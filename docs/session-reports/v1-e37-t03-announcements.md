# Session report: v1-e37-t03-announcements

| | |
|---|---|
| Task | `v1-e37-t03-announcements` — Announcements and news |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t03-announcements.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t03-announcements.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t03-announcements` |
| Session status | COMPLETE for the session; ac5's operator run is outstanding, so the Goal stays InProgress |

## Summary

Announcements are Markdown files in `site/content/announcements/`, one per item, built into a home
page band (every pinned item, then the three newest), a `/news/` list (newest first) and a page per
item at `/news/<file name>/`. `src/lib/announcements.ts` checks every file at build time, in every
environment, and names the file and the rule in `docs/policies/website-publishing.md`. The checks
are the schema, Markdown only (raw HTML refused, not stripped), house style, and the existing
publishing-policy guard, extended rather than duplicated. The guard's two gaps from the v1-e36-t08
review are closed, and both were shown failing first (commit `b2934c1`): the name rules now read
alt text and captions, and a one-word allowlist entry fails the build unless it is on a short
reviewed list. The coach guide's Google Sheet section is replaced. **The Goal stays InProgress:**
ac5's second half, Charlie publishing and then expiring one real announcement through dev and prod,
is an operator run (blocks under [Operator follow-ups](#operator-follow-ups)). Everything else
passed. Worth reading first: [Deviations](#deviations-from-the-spec). Closing ac6 turned up three
small holes in the same guard, which I fixed and list there.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `policy-validator` (the two gaps' red run) | Done first, as ruling 6 asks | Commit `b2934c1`: the tests fail against the old guard. Commit `fa56d17` closes them |
| `schema-and-fixtures` | Done | Front-matter schema in `src/lib/announcements.ts`; fixtures in `site/tests/fixtures/announcements/` (`season/` with hand-written expected pages, `refused/` with one file per rule and a valid file) |
| `policy-validator` | Done | Every rule in ac3, ac6 and ac7 has a fixture that fails naming the file and the rule, and the valid fixture publishes |
| `pages` | Done | Home band, `/news/` and item pages from one optional catch-all route; sitemap; layout guard wiring |
| `guide` | Done | `docs/guides/coach-website-editing.md`, section "Announcements: one file each in the announcements folder" |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: home shows pinned then the three newest non-expired, `/news/` lists all non-expired newest first, each item has its own page with title, date and body | PASS | `tests/announcements.test.tsx` ("which announcements are published", "the home page", "the /news/ page", "an announcement's own page"), expected orders written by hand from `fixtures/announcements/season/` at build date 2026-11-02. Real export with two temporary invented items (removed afterwards): `/news/2026-10-30-novice-orientation/index.html` written, home band showed it with "Pinned" |
| ac2: an item expired before the build date is on no page and not in the sitemap | PASS | Same file: "hides an expired item even when it is pinned", "the sitemap … no expired or future one", "shows an item expiring on a date through that date, and drops it from the first build after it". The temporary real build: the expired item was in neither `index.html`, `news/index.html` nor `sitemap.xml` (`grep -c` → 0, 0, 0) |
| ac3: the validator rejects a non-allowlisted "First Last", an email, a phone number, a script or iframe, an image without consent, naming the item and the policy rule; valid items still publish | PASS | `describe('the publishing-policy rules')`: one fixture per rule in `fixtures/announcements/refused/` (plus raw HTML, a `javascript:` link and a remote image). Each test asserts `content/announcements/<file>.md: … (docs/policies/website-publishing.md, <rule>)`, and `valid.md` beside them publishes. Shipped-content plants: `tests/shipped-content.test.ts` "an announcement planted in a copy of the shipped content" |
| ac4: the guide covers add, change, pin, expire, remove, the publish path under ADR-0015 point 4, expiry at the next deploy, and what may never be written; no Google Sheet | PASS | `grep -ci sheet docs/guides/coach-website-editing.md` → 0; sections Add, Schedule one for later, Change, Pin and unpin, Expire ("Expiry takes effect at the next deploy, not on its date"), Take down, Pictures, What may never be written, What the build refuses; "Which publish path" names the site lane under point 4. `uv run scripts/check_links.py` → `OK: 3453 relative links and anchors in 576 Markdown files`; `uv run scripts/check_command_blocks.py` → OK |
| ac5: `pnpm --dir site lint`, `typecheck`, `test` and `build` pass offline | PASS | `site/scripts/pre-commit-checks.sh` with `SITE_ENV=dev` (lint, typecheck, test, build, export checks), exit 0 in 20 s: `28 passed` files / `1063 passed` tests (baseline 969), export checks `13 passed` / `114 passed`. Prod: `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh`, exit 0, `114 passed`. Install was `pnpm --dir site install --offline --frozen-lockfile` from the local store; pnpm not updated |
| ac5: Charlie publishes and then expires one real announcement end to end through dev and prod | **NOT RUN** | Operator run with a push, deploys and Charlie's words; blocks under [Operator follow-ups](#operator-follow-ups). The PM records it |
| ac6: name rules read alt text and figure captions; a "First Last" in alt fails with the body-copy message; fixture proves it | PASS | Red first (`b2934c1`, run saved before the fix): 10 failed / 4 passed. A name in a Markdown image's alt, an HTML `alt` (both quote styles), a Markdown caption (`"title"`), a built page's `alt`, an apostrophe name (`O&#39;Neill`) and a bold first name all **passed the old guard**. A `<figcaption>` was already caught, being element text. Green after `fa56d17`: each now gets `toBe` the body-copy message. Announcement fixtures `refused/name-in-alt-text.md` and `name-in-caption.md` produce the same `[message, rule]` as `student-name.md` |
| ac7: the allowlist stays reviewed phrases; a new bare word outside a short reviewed list fails | PASS | Red first: "refuses a new bare word" → `expected [Function] to throw an error` against the old manifest schema. Green: `permittedNamePhrases: "Ellery" is a single word. …` from `loadMediaConsent`. `REVIEWED_SINGLE_WORDS` (31 entries: The, In, Email, Joining, Outlook, the days with their plurals, the months) is checked short and free of any consented name's words |
| Node `schema-and-fixtures`: `pnpm --dir site test` | PASS | `Test Files 28 passed (28)`, `Tests 1063 passed (1063)` |
| Node `policy-validator` (custom): each rule failing on a fixture, valid fixtures publish | PASS | As ac3, ac6, ac7. Ten planted breaks, each run against `tests/announcements.test.tsx` and `tests/content-policy.test.ts` and restored with `git checkout HEAD --`, all caught at assertions: expiry day made exclusive (7 failed), future items published (9), pinned counted toward the three (3), raw HTML let through (5), policy guard skipped (8), any link accepted (3), slug collision ignored (1), student name in a slug ignored (1), alt text not read (9), bare words accepted (1) |
| Node `pages`: `pnpm --dir site build` | PASS | `SITE_ENV=dev node site/scripts/build-export.mjs` → `recorded 85 exported files`; route table shows `/news/[[...slug]]` → `/news` |
| Node `guide`: the guide exists and contains `site/content/announcements` | PASS | `grep -c "site/content/announcements" docs/guides/coach-website-editing.md` → 4 |

**Before the report** (working agreement 10):

- `uv run scripts/affected_tests.py --run` under `scripts/hard_stop.py 115`: 60 test files chosen
  (none tests the site; most are false edges through file-name words). The run was stopped at its
  115-second limit at 91 % with no failure or error in the output. The load average was 7.9 at the
  start. Per agreement 10 the rest is left to the pull request's `ci`, which runs the same affected
  set.
- The always-run list (8 files) on its own: `240 passed in 21.01s`.
- `uv run ruff format --check` → `1862 files already formatted`; `uv run ruff check` → `All checks passed!`;
  `uv run lint-imports` → `Contracts: 20 kept, 0 broken`. No Python file changed, so `pyright` has no
  changed package to check.
- `uv run --frozen python scripts/docs_index.py --check-descriptions` → all 68 have a description;
  `uv run scripts/validate_specs.py` → `OK: 585 files, 41 epics, 522 tasks, 22 releases`.
- The task spec matches the local `origin/dev` ref apart from the phase line. The ref is not
  re-fetched: no network call this session.

## Files changed

- `site/src/lib/announcements.ts` (new): the loader, the checks, the build date, which items are
  published and in what order, and the guard's view of them.
- `site/src/lib/publishing-policy.ts`: `visibleText` reads alt and title attributes, decodes
  entities, and reads inline formatting as part of a run. The capitalised-word pattern reads O'Neill
  whole. Findings carry `rule`, and `describeFinding` prints it.
- `site/src/lib/media-consent.ts`: `REVIEWED_SINGLE_WORDS`, and the manifest schema refuses any
  other one-word `permittedNamePhrases` entry.
- `site/src/lib/content.ts`: `NEWS_SLUG` (a composed page), `renderMarkdown` exported, the home
  band's words in the schema, and the `announcementFields` comment.
- `site/src/app/news/[[...slug]]/page.tsx` (new), `site/src/components/AnnouncementSummary.tsx`
  (new), `site/src/app/page.tsx` (the band), `site/src/app/sitemap.ts`, `site/src/app/layout.tsx`
  (guard wiring), `site/src/styles/sections.css`.
- `site/content/`: `announcements/README.md` (explains the folder, never published),
  `pages/news.md`, `news.yaml`, the `announcements` words in `home.yaml`, and a comment in
  `media-consent.yaml`. No real announcement is shipped; that is ac5.
- `site/tests/`: `announcements.test.tsx`, `announcements-fixture.ts`, `build-date.ts`, fixtures in
  `fixtures/announcements/`, `export/announcements.export-test.ts`. `setup.ts` pins the build date;
  additions to `content-policy.test.ts`, `shipped-content.test.ts` and `pages-a11y.test.tsx`.
- `site/README.md`, `docs/guides/coach-website-editing.md`.

## Deviations from the spec

1. **Three more holes in the name rules, fixed with the two the spec names.** Closing ac6 showed
   that the guard missed names in three more shapes, in every page and not just announcements:
   - A name with an apostrophe in rendered HTML. The renderer writes `O'Neill` as `O&#39;Neill`,
     which no run of capitals matches, so the name was never seen.
   - A name split by inline formatting, such as `**Rowan** Ellery`. Every tag became a space, so the
     two words were read as two runs.
   - O'Neill even in plain text. The word pattern stopped at the capital after the apostrophe, so it
     was reported as `O'`, though it was still caught.

   All three are fixed in `publishing-policy.ts`, each with a test, and every existing test still
   passes. The spec's description names only alt text and captions; the PM may want it to name these
   too.
2. **Findings now carry the policy rule, and the layout guard prints it.** ac3 asks for the rule to
   be named. The rule is a new optional field on the guard's findings, rather than text matched out
   of messages, so the page guard's printed problems gain a `(docs/policies/website-publishing.md,
   <rule>)` suffix as well. Messages themselves are unchanged.
3. **Rules beyond ac3's list, under the spec's forbidden list** (unsanitized HTML, scripts, embeds):
   - A Markdown link that is not to a page here, `https://`, `http://` or `mailto:` is refused,
     since marked does not sanitise, so `javascript:` would otherwise run.
   - A Markdown image from another site is refused.
   - A file name carrying a consented student's whole name is refused. It is reported by position,
     not by name (Students 10), because the file name is the published address.
   - Any non-`.md` file in the folder is refused.

## Decisions and assumptions

- **File name and slug (ruling 3).** The slug is the file name without `.md`, lower-cased, with
  accents folded and every other run of characters made one hyphen. `2026-11-03-novice-orientation.md`
  publishes at `/news/2026-11-03-novice-orientation/`. The guide asks for date-first, lower-case,
  hyphenated names, which keep the folder in date order and never repeat across years. **Two files
  that come to one slug** (`Novice Orientation.md` and `novice-orientation.md`) are both refused at
  build, with one message naming both, and neither publishes.
- **A future `date` is not yet published.** The spec calls it a "publish date" and the old guide said
  "the day it should first appear", so an item appears from the first build on or after its date.
- **Expiry (ruling 2).** An item is published when `date <= build date <= expires`. The build date is
  `SITE_BUILD_DATE` when set, otherwise today in America/Chicago (`Intl`, tested at both UTC
  offsets). `tests/setup.ts` sets it to 2026-11-02 for every test, from `tests/build-date.ts`. The
  code's only clock read is a default argument, and every test that exercises it passes an instant.
  `SITE_BUILD_DATE` is accepted in every environment; the deploy blocks already refuse a leftover
  `SITE_` variable, and the export fingerprint records it when set.
- **Home order (ruling 1)** is `homeAnnouncements`: pinned newest first, then the three newest
  unpinned. A pinned item doesn't count toward the three, and an expired item is gone before this
  runs.
- **Every file is checked, published or not**, so a problem shows the day a file is written. The
  catch: a file naming a student whose consent has lapsed fails even after it expires. The guide
  says to delete expired files at the end of the season.
- **Fatal in every environment**, as for the schedule and the results (the dev preview is public). A
  `[[TBD]]` marker follows the page rule instead: a badge in dev, fatal in prod, through the layout
  guard. `announcementFields()` stays empty because Markdown announcements have no unset-able
  field; its comment says so.
- **One optional catch-all route.** Next 16 refused the two-route version at build:
  `Page "/news/[slug]" returned an empty array from "generateStaticParams()". With "output: export",
  at least one route must be generated.` The site will usually have no announcements, so
  `src/app/news/[[...slug]]` always generates `/news/` and adds one page per published item.
- **A bug found by the first real build:** gray-matter's cache returns a copy without `matter` (the
  raw front matter), so the second read of a file in one process failed. The loader passes an
  options object, which skips the cache, and a test reads a folder twice.
- **`/news/` is in the footer, not the header navigation.** It is not in `primaryNavigation`, so it
  joins the footer's utility links, and the home band links to it. Adding it to the header is a
  one-line `site.yaml` edit if Charlie wants it.
- **Visual QA (ruling 7).** The QA command walks the sitemap (pinned by
  `tests/export/visual-qa.export-test.ts`), so `/news/` and every published item are in it with no
  change. No screenshots are committed (`site/qa-artifacts/` is gitignored by policy), so there are
  no baselines to produce. The browser run is part of the ac5 blocks; freshness is left to
  v1-e36-t11.
- **Smoke checks.** `scripts/site_smoke.py` reads every page in the sitemap, so `/news/` and each
  item are checked with no change (and `scripts/` is outside this task's packages).

## Operator follow-ups

**ac5: publish one real announcement through dev and prod, then expire it.** This is the site lane
from the guide's [Publish a change](../guides/coach-website-editing.md#publish-a-change)
(ADR-0015 point 4, v1-e37-t09), applied to an announcement. Two runs on two different days: one to
publish, then one at least a day later to expire. The PM records the result.

Rules for every block below:

- **Never on a Wednesday while the cloud run is going.** Each block that changes something refuses
  to run on a Wednesday.
- **The announcement names no student** unless that student's entry in
  `site/content/media-consent.yaml` is current for 2026-27 and allows the full name. The safe choice
  for this check is one that names nobody, such as a meeting or a deadline. One that names a
  student needs Charlie to have read it before it publishes (checklist item 16).

**0. Before the first run: is the feature on `main`?** This task merges into `dev`. The lane builds
from `main`, so the announcements code has to be there first, either from the next promotion or
from the guide's [Bringing dev's site to main](../guides/coach-website-editing.md#bringing-devs-site-to-main),
with Charlie's word. A read-only check (a few seconds):

**Operator command**
Where: the `dev-preview` worktree
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git fetch origin
git cat-file -e origin/main:site/src/lib/announcements.ts && echo "OK: announcements are on main" || echo "STOP: announcements are not on main yet"
```

**Publishing it** (the lane takes about an hour, most of it waiting for checks). Every block runs
in one terminal window, because the first sets `SITE_BRANCH` and `ANNOUNCEMENT`. Name the
announcement for today and what it says, lower case with hyphens; it becomes the address
`/news/<name>/`.

**Operator command**: start the branch
Where: the `dev-preview` worktree
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
ANNOUNCEMENT=2026-11-05-first-announcement
SITE_BRANCH=site/announcement-${ANNOUNCEMENT}
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; elif [ -n "$(git status --porcelain)" ]; then echo "STOP: dev-preview has uncommitted changes:"; git status --short; else git fetch origin && git switch -c "${SITE_BRANCH}" origin/main && pnpm --dir site install --frozen-lockfile; fi
```
Change `ANNOUNCEMENT` to today's date and two or three words first. Success looks like `Switched
to a new branch`, and pnpm ending `Done`.

**Write the file.** Create `site/content/announcements/<ANNOUNCEMENT>.md` in an editor, as in the
folder's `README.md`. Give it a `title`, today's date as `date`, no `expires` yet and no image, and
a short body that names no student (see above).

**Operator command**: check it and commit it (about a minute)
Where: the same window
```bash
pnpm --dir site lint && pnpm --dir site typecheck && pnpm --dir site test
SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh
test -f "site/out/news/${ANNOUNCEMENT}/index.html" && echo "OK: the page is in the export" || echo "STOP: no page for ${ANNOUNCEMENT} in the export"
git add site/content/announcements
git commit -m "Announcement: ${ANNOUNCEMENT}"
uv run scripts/check_promotion_source.py site-only --head "${SITE_BRANCH}"
```
Success looks like the tests and export checks passing, `OK: the page is in the export`, and `OK:
Every one of the N changed path(s) is under site/ …`. A build that stops on an announcement names
the file and the rule: fix it and run the block again.

**Operator command**: the dev deploy's dry run (about a minute)
Where: the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else aws sso login --sso-session debate && env | grep -E '^(DEBATE_|SITE_)' && echo "Stop: unset the variables printed above, then run this block again" || scripts/site_deploy.sh dev --dry-run; fi
```
Read before going on. The build prints no "Publishing policy problems" block, and the route list
shows `/news/<ANNOUNCEMENT>`. Any finding, or a printed `DEBATE_`/`SITE_` variable, stops here.
A leftover `SITE_BUILD_DATE` would publish as of the wrong day.

**Operator command**: the dev deploy (about four minutes)
Where: the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else env | grep -E '^(DEBATE_|SITE_)' && echo "Stop: unset the variables printed above, then run this block again" || scripts/site_deploy.sh dev; fi
uv run scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
git rev-parse HEAD
```
Success looks like `Deployed <sha> to dev`, `All N checks passed.` (N counts `/news/` and the
announcement's page), and the visual QA exiting 0 with `/news/` and `/news/<ANNOUNCEMENT>/` at 95
or above. Then read `https://dev.wfbdebate.com/` and the announcement's page on a phone. The
announcement is in the home page's "Announcements" band and on `/news/`. The last line is the
commit for the pull request's `Dev build:` line.

**Then steps 5 to 10 of [Publish a change](../guides/coach-website-editing.md#publish-a-change),
unchanged:** push and dispatch `validate-dev`, open the pull request with the site template, merge,
deploy prod from `prod-deploy` (its dry run first: `scripts/site_deploy.sh prod --dry-run`, then
the deploy block), merge the back-merge into `dev`, and return `dev-preview` to `dev`. Step 6 needs
the checklist ticked, and item 16 if the announcement names anyone. After the prod deploy, a
read-only check (a few seconds):

**Operator command**
Where: any shell in the same window
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://wfbdebate.com/news/${ANNOUNCEMENT}/"
curl -sS https://wfbdebate.com/sitemap.xml | grep -c "/news/${ANNOUNCEMENT}/"
```
Success looks like `200`, then `1`. Paste both back for the PM.

**Expiring it**, on a later day (not a Wednesday). In a new window, set `ANNOUNCEMENT` to the same
name and `SITE_BRANCH=site/expire-${ANNOUNCEMENT}`, then run the same start-the-branch block. Add
`expires: <the announcement's own date>` to its front matter. That is the last day it shows, so the
build that day drops it. Run the same check-and-commit block, except that the `test -f` line must
now print `STOP: no page …`, and its commit message is `Expire announcement: ${ANNOUNCEMENT}`. Then
deploy dev and prod as above. The deploy syncs with `--delete`, so the page leaves the bucket. After
the prod deploy:

**Operator command**
Where: the same window
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://wfbdebate.com/news/${ANNOUNCEMENT}/"
curl -sS https://wfbdebate.com/sitemap.xml | grep -c "/news/${ANNOUNCEMENT}/"
curl -sS https://wfbdebate.com/news/ | grep -c "${ANNOUNCEMENT}"
```
Success looks like anything but `200` on the first line (the not-found page), then `0` and `0`.
That closes ac5; the PM then sets the Goal to Succeeded.

## Follow-up work

- **Graduated students and lapsed consent in announcements** (policy, Charlie; same family as
  v1-e37-t06's follow-up for results). The policy says an announcement naming a graduated student
  "stays, as published, and expires on its own schedule". The build refuses a name whose consent
  is not current for the season, so from 1 August 2027 any file naming a 2026-27 student fails the
  build until it is edited or deleted. That is safe, but the policy says otherwise. The PM's
  rollover task could cover both.
- **Published form of a name in free text.** The guard accepts a consented student's name without
  the "(2028)" the policy's published form adds, on announcements and on every page. Results
  enforce the form; free text does not.
- **Reviewed single words can still pair up.** Every word in a run must be covered, so a single
  reviewed word never covers a name on its own. But a name made only of reviewed words, such as a
  student called "April May", would pass. This is a residual of keeping the months.
- **The image file is not checked to exist, and EXIF is not checked.** A mistyped `image` path in
  both the announcement and the manifest would ship a broken image. EXIF stripping (Photos 6) stays
  a manual step, as the guide says.
- **The policy text.** `docs/policies/website-publishing.md` still says the full published-names
  allowlist is `v1-e37-t03`. The allowlist is now the manifest's students plus reviewed phrases. A
  sentence for the PM to approve, for "The published-names allowlist": *"The allowlist is
  `site/content/media-consent.yaml`: its `students`, and `permittedNamePhrases`, which holds
  reviewed phrases only; a one-word entry is refused unless it is on the short reviewed list in
  `site/src/lib/media-consent.ts`."*

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

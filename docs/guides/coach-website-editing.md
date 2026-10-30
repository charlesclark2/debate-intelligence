<!-- docs-index: For coaches: adding, changing and removing events and announcements on the team website, with no code -->
# Keeping the team website current: a guide for coaches

> **Partly out of date.** The parts about **announcements** still describe the Google Sheet
> proposal, which [ADR-0015](../adr/0015-website-content-editing.md#decision-as-accepted) did not
> adopt; each one is marked. Announcements are becoming Markdown files in
> `site/content/announcements/`, and `v1-e37-t03` rewrites those parts. Everything about **events
> and the tournament schedule** (`v1-e37-t02`) and **the season's results** (`v1-e37-t06`) is
> current.

How the Whitefish Bay debate team website's tournament schedule, results and announcements are
kept up to date, and how a change reaches parents.

Decision behind this: [ADR-0015](../adr/0015-website-content-editing.md#decision-as-accepted).
The rules about students come from the team's publishing policy,
[`docs/policies/website-publishing.md`](../policies/website-publishing.md), which governs if this
guide and the policy ever disagree. How a deploy runs:
[`docs/runbooks/team-website.md`](../runbooks/team-website.md).

## What you can change, and where

| You want to | Where it is done | Who does it |
|---|---|---|
| Add, change or remove a tournament | `site/content/tournaments.yaml`, in the repository ([Events](#events-the-tournament-schedule-file)) | Charlie, in git. A coach who does not use git sends Charlie the change |
| Add, correct or take down a result | `site/content/results.yaml`, in the repository ([Results](#results-the-seasons-results-file)) | Charlie, in git. A coach sends Charlie the tournament's published result |
| Post, change or take down an announcement | *Out of date:* see [Announcements](#announcements-the-website-announcements-sheet) | |
| Change anything else on the site (the pages about the team, the events explained, the coaches, the parent questions) | `site/content/` | Charlie. Anyone else asks Charlie |
| Put a photograph on the site | Send it to Charlie. **Never** put a photo in a content file yourself | Charlie, after checking consent |

## Never post these about students

Everything in the tournament schedule and in an announcement is **public**: anyone can read it,
including people who are not parents, and the schedule is also copied into every subscriber's
calendar app. The team's publishing policy protects students who are minors, and these rules have
no exceptions.

- **No student contact information, ever.** No email address, phone number, social media
  handle, home address or bus route for any student.
- **No student names in the tournament schedule, at all.** Write "the Public Forum teams", not
  names. An announcement can name a student only if their family's media-consent form for this
  season is on file and Charlie has checked it.
- **No photos.** Photos go through Charlie, who checks consent for every person in the picture.
- **Never place a named student at a time and place.** "The bus leaves at 6:30 AM" is fine.
  "Jordan rides with Mr. Smith" is not, and neither is a hotel room list or a roster.
- **Nothing sensitive about any student.** No grades, discipline, health, family matters or
  team-selection decisions.

When in doubt, leave it out, or write at team level ("A Whitefish Bay team reached the
quarterfinals") and ask Charlie.

The build enforces part of this: a schedule entry containing an email address, a phone number or
a capitalised name nobody has reviewed **fails the build**, in the dev preview as well as in prod,
and the message names the tournament and the field. That is a backstop, not permission. It cannot
tell a ride list from a bus time.

## Events: the tournament schedule file

The season is one file: **`site/content/tournaments.yaml`**. Two things are built from it and
nothing else:

- the **Tournament Schedule** page, `/schedule/`, which lists the whole season in date order with
  the national tournaments in a section of their own;
- the **calendar file**, `/schedule.ics`, which parents subscribe to from that page in Google
  Calendar, Apple Calendar or Outlook.

There is no Google Calendar, no shared account and nothing fetched from anywhere. The file is the
source of record. (`docs/data/2026-27-tournament-schedule.md` was the seed for it and is no longer
updated.)

The comment at the top of the file lists every field. In short:

| Field | What to put | Example |
|---|---|---|
| `id` | Lower case and hyphens, **ending in the year**. Never changed once published, never reused | `glenbrooks-2026` |
| `name` | The tournament's name, written out (no "HS", "WI" or "WFB") | `Brookfield East High School` |
| `start` | The first day, as year-month-day | `2026-11-21` |
| `end` | The last day, only for a tournament of more than one day | `2026-11-23` |
| `events` | Any of `policy`, `lincoln-douglas`, `public-forum` | `[lincoln-douglas, public-forum]` |
| `held` | `in-person`, `online-at-school` (online, but debated at Whitefish Bay High School, so students come to school), or `online-from-home` | `online-at-school` |
| `where` | Where students go: town, or school and town. Required for `in-person`; left out for the online kinds. `To be announced` is an answer | `Madison, Wisconsin` |
| `overnight` | `no`, `yes` or `possibly` | `possibly` |
| `status` | `confirmed`, `tentative`, or `conditional` | `tentative` |
| `condition` | Only with `conditional`: the sentence saying what it depends on. The page shows it in full | |
| `signUpBy` | Optional: the date families must have signed up by | `2026-10-30` |
| `notes` | Optional: one or two short sentences | `Varsity only.` |
| `nationals` | `true` for a national tournament | `true` |

**Update `revised`** at the top of the file to the day you make any change. The page shows it as
"Schedule last updated", and calendar apps are given it as the date each event was issued.

### Add a tournament

1. Add an entry anywhere in the `tournaments:` list. The order in the file does not matter; the
   page sorts by date.

   ```yaml
     - id: marquette-2027
       name: Marquette University High School
       start: 2027-02-06
       events: [policy, lincoln-douglas, public-forum]
       held: in-person
       where: Milwaukee, Wisconsin
       overnight: no
       status: confirmed
       notes: Bus leaves the high school at 6:30 AM.
   ```

2. **If the events are held differently**, describe each group under `byEvent` instead of `events`,
   `held`, `where` and `overnight`. This is what Glenbrooks needs: Lincoln-Douglas and Public Forum
   debate online from the high school, Policy travels to Illinois.

   ```yaml
     - id: glenbrooks-2026
       name: Glenbrooks
       start: 2026-11-21
       end: 2026-11-23
       byEvent:
         - events: [lincoln-douglas, public-forum]
           held: online-at-school
           overnight: no
         - events: [policy]
           held: in-person
           where: Glenview, Illinois
           overnight: yes
       status: confirmed
       notes: Varsity only.
   ```

   Never describe a tournament debated from the high school as in person somewhere else, or
   leave it to `notes`: whether a student needs a ride to school is what `held` is for.

3. **If it is not certain**, say so. `tentative` for a date or place still to be confirmed.
   `conditional` with a `condition` for one that happens only if something else does:

   ```yaml
       status: conditional
       condition: >-
         Our team hosts this tournament. Our students compete in it only if enough families
         volunteer to help run it and some students still need qualifying results, called legs,
         for the state tournament.
   ```

4. **If the build names something new**, such as a host school it has not seen before, it fails
   with a message like `names "Fort Atkinson", which has no entry in content/media-consent.yaml`.
   If it is a school, a tournament or a place, add the whole phrase to `permittedNamePhrases` in
   `site/content/media-consent.yaml`. If it is a person, take it out of the schedule.

5. Update `revised`, then check it builds (see [Check a change](#check-a-change)).

**Two tournaments on the same dates** need nothing from you. The build works out which entries
share a day and marks both on the page ("Same dates as ...") and in each calendar event. Keep both
entries: never merge them, and never drop one because the team will only send students to the
other.

### Change a tournament

Edit the fields that changed, update `revised`, check it builds, and publish.

- **Never change the `id`.** A calendar app knows each tournament by it, so a new `id` is a
  different event. A parent who subscribed loses any reminder they set on the old one, and a parent
  who downloaded the file once and imported it gets a second copy that never goes away. Everything
  else (dates, name, place, status, notes) can change freely: the existing event moves or updates.
- A tournament that has happened **comes off the page**: delete its entry at the next edit, as
  under "Remove a tournament" (Charlie's decision of 2026-10-22). The page shows the rest of the
  season. How the team did goes in the season's results, not the schedule.

### Remove a tournament

Delete its entry, update `revised`, check it builds, and publish. It comes off the page at the
deploy, and off subscribers' calendars the next time their app checks the file.

If the team has simply decided not to go, consider whether families would rather see that than
have the tournament vanish: a note such as `The team is not attending this tournament.` keeps it
visible until the next deploy after the date.

**At the start of a new season**, change `season` (for example to `'2027-28'`) in three files, in
one edit: `site/content/tournaments.yaml`, `site/content/results.yaml` and
`site/content/media-consent.yaml`. The site's tests check that the three are for the same season,
so changing one of them alone fails. In the same edit:

- in the schedule, replace the entries with the new season's, update `revised`, and use new `id`s
  with the new year;
- in the results, take out last season's results (leave `results: []` until the new season's
  first) and update `revised`;
- in the consent file, change only `season`. Every consent entry lapses with the season, so Charlie
  runs the policy's
  [start-of-season check](../policies/website-publishing.md#consent-renewal-and-the-start-of-season-check)
  and brings each entry up to date before the change is published; until then the site's tests
  fail on every entry not yet brought up to date.

The build refuses a date outside the season, which is what catches a typed year left over from
last season.

### Check a change

From the repository root. The last command starts the site locally; then open
<http://localhost:3000/schedule/>.

```bash
pnpm --dir site test
SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build
pnpm --dir site dev
```

The build fails, naming the tournament and the field, on a mistake in the file: a misspelt field,
a date that does not exist, an `id` used twice, a conditional entry with no condition, a place on
a tournament debated from the high school, a name nobody has reviewed, an email address or a phone
number. Fix what it names and run it again.

**A content edit never needs a test edit.** The site's tests check `site/content/tournaments.yaml`
and `site/content/results.yaml` only for what has to be true of them whatever they hold: they
load without a mistake, they pass the publishing-policy and consent checks, no `id` is used twice,
every date is inside the season, and the schedule, the results and the consent file are for the
same season. Everything else (the page's order, the calendar file, the results page) is tested on
made-up tournaments and results of the tests' own. So adding, changing or removing a tournament
or a result, and moving a result to `tournament` and `date` once its tournament is off the
schedule, passes `pnpm --dir site test` without touching anything under `site/tests/`.

If a test fails after an edit that changed only files in `site/content/`, read the message
first: a mistake in the edit is named the same way the build names it, by file, entry and field,
and fixing it is the whole job. If the message names no mistake in what you changed, **that is a
bug in the tests, not a test to change.** Report it to Charlie with the name of the failing test,
and don't edit the test or publish the change until Charlie answers.

### Publish a change

A change to the file is a commit, and nothing reaches the public site except from `main`
([ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md),
[ADR-0015](../adr/0015-website-content-editing.md#decision-as-accepted) point 4). A change to the
website's content, pages or assets has a lane of its own, **the site lane**, which takes it to the
public site the same day without waiting for the next release
([`v1-e37-t09`](../../plan_specs/v1/e37-calendar-and-announcements/t09-site-changes-publish-without-a-release.yaml)).
Use it for every schedule change, every result, every correction and every takedown.

**What the lane is.** A `site/<what-changed>` branch from `main`, a pull request from it into
`main`, the operator's deploy, and the back-merge into `dev` the same day. GitHub refuses the pull
request if the branch changes anything outside `site/`, changes a dependency manifest or lockfile
(`site/package.json`, `site/pnpm-lock.yaml` and the like), or changes nothing: those go through a
promotion of `dev`. Before it can merge, `validate-dev` builds the commit **for prod**, where the
publishing-policy and consent guards stop the build on an unfilled consent reference, a `[[TBD]]`
marker or a name nobody has reviewed, and runs the export checks against that build. The policy's
[pre-publication checklist](../policies/website-publishing.md#pre-publication-checklist) is in the
pull request's template, and item 16 is unchanged: anything that names a student needs Charlie to
have seen it.

**Before you start.** The lane needs **the Mac that holds the `prod-deploy` and `dev-preview`
worktrees** (the runbook's [deploy worktrees](../runbooks/team-website.md#the-deploy-worktrees)),
signed in to `gh` and to the AWS SSO session, with `pnpm` and `uv`. Every block below runs in one
terminal window, because the first one sets `SITE_BRANCH` for the rest. The whole lane takes about
an hour, most of it waiting for checks.

**1. Start the branch** in the `dev-preview` worktree. Name it for what changes, one word or a
few joined with hyphens: `site/results-ronald-reagan`, `site/schedule-2026-11-07`. The block
refuses if that worktree holds uncommitted changes, which would be someone's unfinished work.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
SITE_BRANCH=site/results-ronald-reagan
if [ -n "$(git status --porcelain)" ]; then echo "STOP: dev-preview has uncommitted changes:"; git status --short; else git fetch origin && git switch -c "${SITE_BRANCH}" origin/main && pnpm --dir site install --frozen-lockfile; fi
```

Success looks like `Switched to a new branch 'site/results-ronald-reagan'`, and pnpm ending
`Done`.

**2. Make the change** in `site/content/` (the schedule, the results, the consent file), as the
sections above describe, and update `revised`.

**3. Check it, and commit it.** The first line is the site's own checks; the second is the prod
build and the export checks, which is what `validate-dev` will run; the last line asks the same
question GitHub will, so a refusal shows here first.

```bash
pnpm --dir site lint && pnpm --dir site typecheck && pnpm --dir site test
SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh
git add site
git commit -m "Results from the Ronald Reagan tournament"
uv run scripts/check_promotion_source.py site-only --head "${SITE_BRANCH}"
```

Success looks like the tests and the export checks passing, and the last line printing
`OK: Every one of the N changed path(s) is under site/ and none is a dependency file.` A build that
stops on a publishing-policy problem names the file and the field: fix the fact and run the block
again from the top. `FAILED` on the last line names what is outside the lane; take it off the
branch.

**4. Preview it on dev** and read it on a phone, as a parent would. The deploy takes about four
minutes, most of it the invalidation.

```bash
aws sso login --sso-session debate
scripts/site_deploy.sh dev
uv run scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
git rev-parse HEAD
```

Success looks like `Deployed <sha> to dev`, then `All N checks passed.` The last line prints the
commit: it goes on the pull request's `Dev build:` line.

**5. Push it and ask `validate-dev` to check it.** The dispatch runs from `dev`, whichever branch
is being checked. It takes a few minutes; the second block asks for the status, and is run again
until it says `success` or `failure`.

```bash
git push -u origin "${SITE_BRANCH}"
gh workflow run validate-dev.yml --ref dev -f sha="$(git rev-parse HEAD)" -f site_only=true
```

```bash
gh api "repos/charlesclark2/debate-intelligence/commits/$(git rev-parse HEAD)/status" --jq '.statuses[] | select(.context == "validate-dev") | .state + "  " + .description'
```

Success looks like `success  site only: nothing outside site/ changed since main; prod build,
policy and consent guards and export checks green`. `pending` means it is still running. Nothing
printed for more than a minute after the dispatch means the run refused the commit before
posting anything: `gh run list --workflow validate-dev.yml --limit 3`, then `gh run view <id> --log-failed`
says why. `failure` links the run that failed; fix the branch, commit, and repeat from step 3 (a
new commit needs its own dispatch).

**6. Open the pull request.** This opens GitHub in the browser with the site template filled in.
Write what changes, paste the commit from step 4 on the `Dev build:` line, and tick the checklist:
every item, honestly. Then create the pull request.

```bash
open "https://github.com/charlesclark2/debate-intelligence/compare/main...${SITE_BRANCH}?template=site.md&expand=1"
```

**7. Merge it** when every check is green. The first command waits for them; the second merges
with a merge commit, the only kind `main` takes.

```bash
gh pr checks "${SITE_BRANCH}" --watch
gh pr merge "${SITE_BRANCH}" --merge
```

Success looks like every check `pass`, then `Merged pull request`. A red `promotion-source` names
what is outside the lane. A red `back-merge` means the previous site change, or a hotfix, has not
been merged back into `dev`: do step 9 for it first, then
`gh pr checks "${SITE_BRANCH}" --watch` again.

**8. Deploy prod** from the `prod-deploy` worktree, exactly as the runbook's
[Deploy prod](../runbooks/team-website.md#deploy-prod) says. About five minutes.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/prod-deploy
git pull --ff-only
pnpm --dir site install --frozen-lockfile
git status --porcelain
aws sso login --sso-session debate
scripts/site_deploy.sh prod
uv run scripts/site_smoke.py --env prod --url https://wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
```

Success looks like `clean, on main, and equal to origin/main.`, a clean prod build, the
invalidation completing, and `All N checks passed.` The page has changed for parents now.

**9. Merge `main` back into `dev`, the same day.** The merge into `main` opened a
"Back-merge main → dev" pull request about a minute later. The first command lists it; put its
number in the next two. Merge it with a merge commit, never a squash.

```bash
gh pr list --base dev --head main --state open
```

```bash
gh pr checks <number> --watch
gh pr merge <number> --merge
```

Success looks like the pull request listed, its checks `pass`, then `Merged pull request`. If
nothing is listed after a few minutes, GitHub lost the push: run
`gh workflow run back-merge.yml --ref dev`, which opens it. If GitHub says the pull request
**has conflicts**, see [When the back-merge conflicts](#when-the-back-merge-conflicts).

**10. Put the preview worktree back on `dev`.**

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git switch --detach origin/dev
git branch -D "${SITE_BRANCH}"
```

**Something that is not a website change** still goes the old ways: anything outside `site/`
waits for the next promotion of `dev`, or, if it is urgent, the hotfix path in
[branching and environments](../process/branching-and-environments.md). A change to the site's
dependencies (`site/package.json`, its lockfile) goes into `dev` on a task branch and reaches
`main` at a promotion.

#### When the back-merge conflicts

The back-merge pull request's head is `main` itself, so a conflict cannot be fixed on it. It
happens only when `dev` changed the same lines of `site/` after your branch was cut, which is why
step 9 is the same day. Merge `main` into a branch of `dev` by hand, fix the files git names, and
merge that into `dev` with a merge commit. Then the open back-merge pull request has nothing left
to bring: close it.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git fetch origin
git switch -c back-merge/site-by-hand origin/dev
git merge origin/main
```

Edit each file git lists as conflicted, keeping both sides' changes, then:

```bash
git add site
git commit --no-edit
git push -u origin back-merge/site-by-hand
gh pr create --base dev --head back-merge/site-by-hand --title "Back-merge main → dev, conflicts resolved by hand" --body "Merges main into dev; the automatic back-merge pull request had conflicts in site/."
gh pr checks back-merge/site-by-hand --watch
gh pr merge back-merge/site-by-hand --merge
```

#### Bringing dev's site to main

When a site **feature** has landed on `dev` (a new page, a new section of the home page), the lane
can carry all of `dev`'s `site/` to `main` at once, with Charlie's word. It is steps 1 to 10 with
step 2 replaced by the line below, which makes the branch's `site/` exactly `dev`'s, deleted files
included. The lane refuses it if `dev`'s site dependencies differ from `main`'s: then it waits for
a promotion.

```bash
git restore --source=origin/dev --staged --worktree -- site
```

#### Installing the lane, once

The lane's check has to be on `main` before GitHub will accept a `site/` pull request, because a
pull request's checks run from its merge with `main`. The task that built it merged into `dev`;
one hotfix carries its five guard files to `main`. Run these blocks once, in order, never on a
Wednesday (the weekly cloud run's day; each block refuses one), and not before Thursday
2026-10-29's image deploy has finished.

The first block builds the hotfix branch in the `dev-preview` worktree from `main`, takes the five
files from the task's commit on `dev`, and refuses if `main`'s copies were not the ones the task
started from (then the hotfix would carry someone else's change too).

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; elif [ "$(date +%Y%m%d)" -lt 20261029 ]; then echo "STOP: not before Thursday 2026-10-29's image deploy."; elif [ -n "$(git -C ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview status --porcelain)" ]; then echo "STOP: dev-preview has uncommitted changes."; else cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview && git fetch origin && LANE_COMMIT="$(git log origin/dev -1 --format=%H --grep='^v1-e37-t09-site-changes-publish-without-a-release')" && echo "lane commit: ${LANE_COMMIT}" && LANE_FILES=(scripts/check_promotion_source.py .github/workflows/promotion-guard.yml .github/PULL_REQUEST_TEMPLATE/site.md tests/scripts/test_check_promotion_source.py tests/scripts/test_promotion_guard_workflow.py) && git diff --quiet origin/main "${LANE_COMMIT}^" -- "${LANE_FILES[@]}" && git switch -c hotfix/install-site-lane origin/main && git checkout "${LANE_COMMIT}" -- "${LANE_FILES[@]}" && git commit -m "Hotfix: install the site lane's guard on main (v1-e37-t09)"; fi
```

Success looks like `lane commit:` and a 40-character commit, then `Switched to a new branch
'hotfix/install-site-lane'` and a commit of 5 files. A `STOP:` line, an empty `lane commit:`, or
the block ending without a commit means stop: say what it printed.

The second block checks the branch carries those five files and nothing else, against `main`.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; elif [ "$(git diff --name-only origin/main...HEAD | LC_ALL=C sort | tr '\n' ' ')" = ".github/PULL_REQUEST_TEMPLATE/site.md .github/workflows/promotion-guard.yml scripts/check_promotion_source.py tests/scripts/test_check_promotion_source.py tests/scripts/test_promotion_guard_workflow.py " ]; then echo "OK: only the lane's five guard files differ from main."; else echo "STOP: the branch differs from main in:"; git diff --name-only origin/main...HEAD; fi
```

Success looks like `OK: only the lane's five guard files differ from main.` Anything else: stop.

The third block pushes the branch and dispatches the hotfix pre-release, which builds it and asks
`validate-dev` to validate it, like any hotfix.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else git push -u origin hotfix/install-site-lane && gh workflow run dev-prerelease.yml --ref hotfix/install-site-lane; fi
```

The fourth block asks for the status on the hotfix head; run it until it says `success`, then
note the pre-release it names for the `Dev build:` line. It opens the pull request with the hotfix
template; write "The site lane's guard is not on main" as the incident.

```bash
gh api "repos/charlesclark2/debate-intelligence/commits/$(git rev-parse HEAD)/status" --jq '.statuses[] | select(.context == "validate-dev") | .state + "  " + .description'
```

```bash
open "https://github.com/charlesclark2/debate-intelligence/compare/main...hotfix/install-site-lane?template=hotfix.md&expand=1"
```

The fifth block merges it once every check is green and Charlie has approved it, and the sixth,
after the back-merge pull request has opened, merges that into `dev` (its number from
`gh pr list --base dev --head main --state open`). `dev` already holds these files, so it merges
without conflicts.

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr checks hotfix/install-site-lane --watch && gh pr merge hotfix/install-site-lane --merge; fi
```

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr list --base dev --head main --state open; fi
```

```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day."; else gh pr checks <number> --watch && gh pr merge <number> --merge && cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview && git switch --detach origin/dev && git branch -D hotfix/install-site-lane; fi
```

Nothing is deployed: the hotfix changes no page. From then on, the lane above works.

**What parents see, and when.** The page changes when the prod deploy finishes. A parent who
subscribed sees the change whenever their calendar app next checks the file. The file asks for once
a day, and apps treat that as a suggestion: Outlook checks about every three to six hours, Google
Calendar and Apple's Calendar do not publish a figure, and Microsoft says it "can take more than 24
hours". Nobody on the team can make it faster. For anything urgent on a tournament day, contact
families directly instead of relying on the calendar.

**Something about a student got into the schedule.** Follow the runbook's
[Taking something down on request](../runbooks/team-website.md#taking-something-down-on-request),
on the policy's 24-hour clock. If it has to be gone in minutes, the runbook's
[emergency lever](../runbooks/team-website.md#the-emergency-lever) applies, and for the schedule it
has to remove **both** files the text is in: `schedule/index.html` (with the page's other files in
`schedule/`) and `schedule.ics`.

## Results: the season's results file

How the team's students placed is one file: **`site/content/results.yaml`**. Two things are built
from it:

- the **Season results** page, `/results/`, in the main navigation after the schedule: every
  tournament with a result, newest first, each with its date and every placing won there;
- the **newest results** band on the home page, which shows the three newest placings and links
  to `/results/`. It is left off the home page until the season has a result.

A tournament comes off the schedule once it is over, and its results go here. Results are the
part of the site most likely to name a child, so the rules in the publishing policy's
[Results and awards](../policies/website-publishing.md#results-and-awards) apply to every entry,
and the build enforces most of them.

**Results are facts, taken from the tournament's own published results** (on Tabroom or the
tournament's site). Never from memory, and never estimated. If the published results are not up
yet, wait for them.

One entry per placing. The comment at the top of the file lists every field. In short:

| Field | What to put | Example |
|---|---|---|
| `scheduleId` | The tournament's `id` in `site/content/tournaments.yaml`, **while it is still there** | `west-bend-2026` |
| `tournament` | Or, once it has come off the schedule, the tournament's name | `Fort Atkinson` |
| `date` | With `tournament`: its first day, as year-month-day | `2026-10-17` |
| `end` | With `tournament`: its last day, only for a tournament of more than one day | `2026-11-14` |
| `event` | `policy`, `lincoln-douglas` or `public-forum` | `lincoln-douglas` |
| `division` | `varsity`, `junior-varsity` or `novice` | `varsity` |
| `placing` | One of the placings the site publishes, written in lower case: `first place` to `tenth place`, `top speaker`, `second speaker` to `tenth speaker`, `champion`, `finalist`, `semifinalist`, `quarterfinalist`, `octofinalist`, `double-octofinalist`, `triple-octofinalist`, or `state qualifying leg` for a leg toward the State tournament earned there (never "first" or "second": a leg is not numbered or counted, policy version 1.2) | `quarterfinalist` |
| `students` | Optional. Who placed, exactly as `site/content/media-consent.yaml` writes their name. Leave it out for the team-level form | `[Jordan Rivera]` |

**Update `revised`** at the top of the file to the day you make any change. The page shows it as
"Results last updated".

### Add a result

1. Add an entry to the `results:` list. If the list says `results: []`, replace the `[]` with the
   first entry. The order in the file does not matter; the page sorts by tournament, newest first.

   ```yaml
     - tournament: Marquette University High School
       date: 2027-02-06
       event: lincoln-douglas
       division: varsity
       placing: quarterfinalist
       students: [Jordan Rivera]
   ```

   A Public Forum or Policy result names **both partners or neither**:

   ```yaml
     - scheduleId: west-bend-2026
       event: public-forum
       division: novice
       placing: semifinalist
       students: [Jordan Rivera, Sam Okafor]
   ```

2. **Two awards at one tournament are two entries**, for example first place and top speaker. The
   page shows both under the one tournament. Never combine them into one line, and never add up a
   student's results across tournaments: a record is something this site does not publish.
3. **Naming a student needs a consent entry first.** A student is named only if Charlie has
   confirmed with the activities office that their family's media-consent form for **this season**
   is on file, and has added them to `students` in `site/content/media-consent.yaml` with their
   graduation year and the consent reference. The page prints the name with the graduation year,
   "Jordan Rivera (2028)". If you are not sure, leave `students` out: see the team-level form below.
4. Update `revised`, check it builds (as under [Check a change](#check-a-change), then open
   <http://localhost:3000/results/>), and publish it (as under
   [Publish a change](#publish-a-change)). **A result that names a student needs Charlie to have
   seen the exact line before it publishes** (the policy's
   [Pre-publication checklist](../policies/website-publishing.md#pre-publication-checklist), item
   16).

### The team-level form

Leave `students` out and the result is published without a name: "Quarterfinalist, Varsity
Lincoln-Douglas: a Whitefish Bay debater", or "a Whitefish Bay team" for a partner event. It is
always allowed, and the page shows it exactly like a named result, never as something lesser.

Use it when:

- the student's media-consent form for this season is not confirmed, or you are not sure;
- the student or their family asked for a first name only, or for no name;
- one partner of a partnership may not be named, because then neither is;
- anything about naming them gives you pause.

**You never write a team-level line yourself.** Leaving `students` out is all it takes. The build
also switches a named result to the team-level form **by itself** whenever a named student's
consent entry is not current for the season (a form that lapsed at the start of the season) or
asks for less than the full name. That is why a reduced-name request or a lapsed form is an edit to
`site/content/media-consent.yaml` alone: every result naming that student changes with it.

### Correct a result

Edit the entry, update `revised`, check it builds, and publish. A correction to a name, a placing
or a division that a family has pointed out is published as soon as it can be; one that takes a
student's name off the site is a takedown, below.

### Take a result down

**A request to take down a student's name or a result is met within 24 hours.** That is the
policy's student clock ([Removal on request](../policies/website-publishing.md#removal-on-request)),
it starts when the request arrives, a tournament weekend does not stop it, and nobody is asked for
a reason.

1. **Change the file.**
   - To take a student's **name** off: delete it from `students` in every entry that names them,
     so those results show in team-level form, and delete or change their entry in
     `site/content/media-consent.yaml` as the family asked. The team's result stays; only the name
     goes.
   - To take the **whole result** off, because the family asked for that: delete the entry.
2. **Publish it through the site lane** straight away, not at the next promotion: a `site/`
   branch from `main`, deployed to dev and checked, merged into `main`, prod deployed, and `main`
   merged back into `dev` the same day ([Publish a change](#publish-a-change)). Then follow the runbook's
   [Taking something down on request](../runbooks/team-website.md#taking-something-down-on-request)
   to confirm it is gone.
3. **If it has to be gone in minutes**, the runbook's
   [emergency lever](../runbooks/team-website.md#the-emergency-lever) applies. A result is in two
   places: the `results/` folder, and, while it is one of the three newest, **the home page**
   (`index.html`, `index.txt` and the `__next.*.txt` files at the top of the bucket). Removing the
   home page takes the front page down until the rebuild is deployed, which the policy accepts: a
   missing page is better than a name left up.

### What the build refuses

The build checks every entry and stops, in the dev preview as well as in prod, with a message
naming the entry, the field and the policy rule. It never repeats a student's name in the message.
It refuses:

- a student in `students` with no entry at all in `site/content/media-consent.yaml`;
- a Public Forum or Policy result naming one partner, or a Lincoln-Douglas result naming two;
- a placing that is not on the list, and says so when it describes a loss ("lost in
  quarterfinals") or a record ("went 5-1", "ranked second", a points total, bids);
- a capitalised name in `tournament` or `placing`, because the build cannot tell it from an
  opponent's student, and no opponent student is ever named;
- an email address or a phone number anywhere in an entry;
- a `scheduleId` that is not in `site/content/tournaments.yaml`. A tournament that has come off
  the schedule is written with `tournament` and `date` instead;
- a date outside the season, a date that does not exist, or a field it does not know.

If the build says a tournament's name "has not been told about", and it is a school, a tournament
or a town, add the whole phrase to `permittedNamePhrases` in `site/content/media-consent.yaml`.

### Results in an email

**An email never names a student.** It cannot be taken back once it is in an inbox, so an update
about a tournament says how the team did in team-level words and links to the results page,
`https://wfbdebate.com/results/`, where the names live under the consent rules and can come down on
request. How to send one: [parent-email-updates.md](parent-email-updates.md).

## Announcements: the Website announcements sheet

> **Out of date.** This section describes the Google Sheet proposal, which ADR-0015 did not adopt.
> `v1-e37-t03` replaces it with Markdown files in `site/content/announcements/`.

Each row of the **Announcements** tab is one announcement. The website shows pinned
announcements first, then the newest, on the home page, and every current one on the news page.

| Column | What to put | Example |
|---|---|---|
| **Title** | A short headline | `Novice orientation Tuesday` |
| **Publish date** | The day it should first appear. Pick from the calendar that pops up when you double-click the cell | `9/29/2026` |
| **Body** | The announcement, in plain words. Leave a blank line between paragraphs (on a laptop, **Ctrl+Enter** or **Cmd+Enter** makes a new line inside a cell). A web address is turned into a link | `Come to Room 264 after school...` |
| **Expires on** | Optional. The last day it should appear. Leave empty to keep it up | `10/6/2026` |
| **Pin to top** | Tick to keep it above newer ones. Use sparingly | ☐ |
| **Status** | `Draft` while you are writing. `Publish` when it is ready. `Waiting for Charlie` if it names or pictures a student | `Publish` |

Do not edit the **Published** tab. It fills itself from the rows set to `Publish`, and it is
the only thing the website reads, so drafts never leave the sheet.

`[Screenshot to add: the Announcements tab with one row filled in, and the Status dropdown open]`

### Getting access to the sheet

Charlie shares the sheet with the Google account you already use. You get an email from Google
saying a spreadsheet was shared with you; the sheet is then in Google Sheets and Google Drive under
**Shared with me**. On a phone, install the **Google Sheets** app if you don't have it.

### Post an announcement

1. Open the **Website announcements** sheet and go to the **Announcements** tab.
2. Type in the first empty row: Title, Publish date, Body, and Expires on if it has an end.
3. Read it once more against [Never post these about students](#never-post-these-about-students).
4. Set **Status** to `Publish`, or to `Waiting for Charlie` if it names or pictures any student.
   Charlie checks those against the consent records and changes them to `Publish` once they pass.

The sheet saves as you type. There is no Save button.

On a phone, in the Google Sheets app: open the sheet, tap a cell, and type in the box that
appears. Tap the **Status** cell to pick from the list. A long body is easier to type on a laptop,
and it is fine to start on a phone and finish later with `Draft`.

### Change an announcement

Edit the row. The change appears at the next update, exactly as a new one does.

### Take an announcement down

- **Later, on a set day:** put the last day in **Expires on**.
- **Now:** change **Status** to `Draft`. It comes off at the next update, and the row stays in the
  sheet in case you want it back. Deleting the row does the same.

If an announcement must come down **urgently**, because it names a student or a family has asked,
change the Status **and then call or text Charlie**. Changing the sheet alone does not take it off
the live website until Charlie next publishes the site, and the publishing policy promises
families a 24-hour clock.

## When something goes wrong

| What happened | What to do |
|---|---|
| The build fails naming a tournament and a field | Fix that field. The message says what is wrong with it; the table under [Events](#events-the-tournament-schedule-file) says what each field takes |
| The build says a tournament "names" something | A school, tournament or place: add the whole phrase to `permittedNamePhrases` in `site/content/media-consent.yaml`. A person: take it out |
| A parent sees a tournament twice | Its `id` was changed after it was published. Put the old `id` back. A subscribed calendar drops the extra copy the next time it checks the file; a parent who imported the file once has to delete it by hand |
| A change is on the website but not in a parent's calendar | Their calendar app has not checked the file yet. It will; for anything urgent, contact families directly |
| The build fails naming a result and a field | Fix that field. The message names the policy rule; [What the build refuses](#what-the-build-refuses) says what each one means |
| A family asks for a student's name or a result to come down | Within 24 hours: [Take a result down](#take-a-result-down) |
| `pnpm --dir site test` fails after an edit to `site/content/` only, and the message names no mistake in the edit | A bug in the tests: report it to Charlie with the failing test's name. Never change a test to make a content edit pass ([Check a change](#check-a-change)) |
| A tournament is missing from the page after a deploy | Check its entry is in `site/content/tournaments.yaml` on `main`. A site change or hotfix that was not merged back into `dev` is undone by the next promotion |
| `promotion-source` fails on a `site/` pull request | It names the files: something outside `site/`, a dependency file such as `site/package.json`, or nothing at all. Take them off the branch; a dependency change goes into `dev` on a task branch |
| `back-merge` fails on a `site/` pull request | The previous site change or a hotfix has not been merged back into `dev`. Merge that back-merge pull request ([Publish a change](#publish-a-change), step 9), then check again |
| `validate-dev` never appears on a `site/` commit | The run refused it before posting: `gh run list --workflow validate-dev.yml --limit 3` and `gh run view <id> --log-failed`. Usually the commit is not the branch's head, or the branch changes something outside the lane |
| *Out of date:* your announcement is not on the website after an update | Check its **Status** is `Publish`, its **Publish date** is today or earlier, and **Expires on** has not passed |
| Something about a student is on the site and should not be | **Phone or text Charlie straight away.** Then take it out of the file (or the sheet) and follow [Taking something down on request](../runbooks/team-website.md#taking-something-down-on-request) |

**Who to contact:** Charlie Clark, head coach, at charles.clark@wfbschools.com, or by phone or
text for anything urgent. If Charlie is unreachable and something about a student has to come down,
the second owner listed in
[website-content-accounts.md](../runbooks/website-content-accounts.md#owners) can do it.

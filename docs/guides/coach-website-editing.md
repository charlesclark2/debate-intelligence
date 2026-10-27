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

**At the start of a new season**, replace the entries with the new season's, set `season` (for
example `'2027-28'`) and `revised`, and use new `id`s with the new year. The build refuses a date
outside the season, which is what catches a typed year left over from last season.

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

### Publish a change

A change to the file is a commit, and it reaches the site the way every change does
([ADR-0015](../adr/0015-website-content-editing.md#decision-as-accepted) point 4,
[ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md)). Nothing reaches the public
site except from `main`. Pick one of two paths:

**1. The next promotion: the normal path.** For anything that can wait for the next release of
the site, which is most changes: a new tournament, a change weeks away, a new season.

1. Commit the change on a branch from `dev` and open a pull request into `dev`.
2. When it merges, it goes out with the next promotion: deploy `dev`, smoke-check it, look at
   `/schedule/` on the preview, merge the promotion pull request from `dev` into `main`, deploy
   prod from a clean `main`. The commands are in
   [the runbook's promotion checklist](../runbooks/team-website.md#promotion-checklist).

**2. The hotfix path: a change inside the week.** For a date, place or status change to a
tournament in the coming week, which cannot wait for a promotion. The 2026-09-30 meeting-date
correction went this way.

1. Branch `hotfix/<what-changed>` from `main`, make the change, and commit it.
2. Deploy that branch to dev and smoke-check it, exactly as for a promotion. A hotfix is still
   validated in dev ([branching and environments](../process/branching-and-environments.md)).
3. Open a pull request into `main` with the hotfix template, merge it, and deploy prod from a clean
   `main`.
4. **The same day**, merge `main` back into `dev`, so the next promotion does not undo the fix.

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
2. **Publish it on the hotfix path**, not at the next promotion: a branch from `main`, deployed to
   dev and checked, merged into `main`, prod deployed, and `main` merged back into `dev` the same
   day ([Publish a change](#publish-a-change), path 2). Then follow the runbook's
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
| A tournament is missing from the page after a deploy | Check its entry is in `site/content/tournaments.yaml` on `main`. A hotfix that was not merged back into `dev` is undone by the next promotion |
| *Out of date:* your announcement is not on the website after an update | Check its **Status** is `Publish`, its **Publish date** is today or earlier, and **Expires on** has not passed |
| Something about a student is on the site and should not be | **Phone or text Charlie straight away.** Then take it out of the file (or the sheet) and follow [Taking something down on request](../runbooks/team-website.md#taking-something-down-on-request) |

**Who to contact:** Charlie Clark, head coach, at charles.clark@wfbschools.com, or by phone or
text for anything urgent. If Charlie is unreachable and something about a student has to come down,
the second owner listed in
[website-content-accounts.md](../runbooks/website-content-accounts.md#owners) can do it.

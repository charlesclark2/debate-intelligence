# Keeping the team website current: a guide for coaches

How a coach adds, changes and removes **events** and **announcements** on the Whitefish Bay debate
team website, from a laptop or a phone, without touching code.

Decision behind this: [ADR-0015](../adr/0015-website-content-editing.md). Accounts and who owns
them: [website-content-accounts.md](../runbooks/website-content-accounts.md). The rules about
students come from the team's publishing policy,
[`docs/policies/website-publishing.md`](../policies/website-publishing.md), which governs if this
guide and the policy ever disagree.

> **Status, September 2026.** The team calendar and the announcements sheet are the places you
> edit. The website pages that show them are still being built (the calendar page in
> `v1-e37-t02`, the news list in `v1-e37-t03`). Until they ship, what you add reaches parents who
> subscribe to the calendar, and appears on the website once those pages exist.

## What you can change, and where

| You want to | Where you do it | What you need |
|---|---|---|
| Add, move or cancel a tournament, practice or meeting | The **Whitefish Bay Debate** calendar in Google Calendar | Your usual Google account, added by Charlie |
| Post, change or take down an announcement | The **Website announcements** sheet in Google Sheets | The same Google account |
| Change anything else on the site (the pages about the team, the events explained, the coaches, the parent questions) | Ask Charlie | Nothing |
| Put a photograph on the site | Send it to Charlie. **Never** put a photo in the calendar or the sheet | Nothing |

You never need GitHub, a terminal, a code editor or a new password. If anything in this guide asks
you for one of those, stop and tell Charlie, because something is wrong.

## Getting access

Charlie shares the calendar and the sheet with the Google account you already use. That can be
your school account or a personal one; it only has to be the one you are signed in to on your
phone.

1. You get two emails from Google: one saying a calendar was shared with you, and one saying a
   spreadsheet was shared with you.
2. Open the calendar email and click the link to add the calendar. It then shows up in Google
   Calendar on your laptop and on your phone, under **Whitefish Bay Debate**.
3. Open the sheet email. The sheet is then in Google Sheets and Google Drive under **Shared with
   me**. On a phone, install the **Google Sheets** app if you don't have it.

`[Screenshot to add: the "calendar shared with you" email, and the calendar in the left-hand list]`

On a phone, a shared calendar can be hidden at first. In the Google Calendar app, open the menu
(the three lines at the top left), scroll to **Whitefish Bay Debate**, and tick it. On an iPhone
using Apple's own Calendar app, use the Google Calendar app instead for editing.

## Never post these about students

Everything you put in the calendar or the sheet is **public**: anyone can read it, including people
who are not parents. The team's publishing policy protects students who are minors, and these
rules have no exceptions.

- **No student contact information, ever.** No email address, phone number, social media
  handle, home address or bus route for any student.
- **No student names, unless Charlie has checked.** A student can be named only if their family's
  media-consent form for this season is on file, and only in the form the policy allows. If you
  want to name a student, set the announcement to **Waiting for Charlie** (see below) and Charlie will
  check. **Never put a student's name in a calendar event.** Write "the Public Forum teams", not
  names.
- **No photos.** Photos go through Charlie, who checks consent for every person in the picture.
- **Never place a named student at a time and place.** "The bus leaves at 6:30 AM" is fine.
  "Jordan rides with Mr. Smith" is not, and neither is a hotel room list.
- **Nothing sensitive about any student.** No grades, discipline, health, family matters or
  team-selection decisions.
- **No students as calendar guests.** Never add anyone as a guest on a team calendar event: guest
  email addresses become public.

When in doubt, leave it out, or write at team level ("A Whitefish Bay team reached the
quarterfinals") and ask Charlie.

## Events: the team calendar

The website's calendar page and every parent who subscribed to the calendar read the same
**Whitefish Bay Debate** calendar. Anything you put on it is public.

### Add a tournament

On a laptop, at [calendar.google.com](https://calendar.google.com):

1. Click the day the tournament starts, then **More options**.
2. **Title:** start with `Tournament: ` and then the tournament's name, for example
   `Tournament: Marquette Invitational`.
3. **Dates:** tick **All day**. For a two-day tournament, set the end date to the last day.
4. **Location:** the host school's name and street address.
5. **Calendar:** choose **Whitefish Bay Debate** from the calendar list (it is under the event
   colour). This is the step people most often miss: an event saved to your own calendar does not
   reach the website.
6. **Description:** the first lines, each on its own line, exactly like this:

   ```
   Entry deadline: October 9, 2026
   Events: PF, LD, Policy
   Travel notes: Bus leaves the high school at 6:30 AM. Pack lunch.
   ```

   - **Entry deadline** is the date families must have signed up by, written as month, day,
     year.
   - **Events** lists which debate events the team is entering: `PF` (Public Forum), `LD`
     (Lincoln-Douglas), `Policy`. Leave the line out if you don't know yet.
   - **Travel notes** is anything families need about getting there. Leave the line out if there
     is nothing to say.
   - Anything you write after those lines appears on the website as extra detail.

7. Do **not** add guests, a Google Meet link or attachments.
8. Click **Save**.

`[Screenshot to add: a filled-in tournament event, with the calendar list set to Whitefish Bay Debate]`

On a phone, in the Google Calendar app: tap **+**, then **Event**, and fill in the same things.
The calendar choice is the line with a coloured dot and your email address under the title: tap
it and choose **Whitefish Bay Debate**. Turn on **All-day**. Tap **Add description** for the three
lines.

### Add a practice, meeting or parent event

The same steps, with a different start to the title:

| Kind | Title starts with | Example |
|---|---|---|
| Practice | `Practice: ` | `Practice: Novice practice` |
| Meeting | `Meeting: ` | `Meeting: Team meeting` |
| Something for parents | `Parent event: ` | `Parent event: Parent information session` |
| A deadline with no event | `Deadline: ` | `Deadline: Nationals qualifier registration` |

These have a start and end time instead of **All day**. For a practice every week, choose
**Does not repeat** and change it to **Weekly on Tuesday** (or whatever day). Put the room in
**Location**, like `Whitefish Bay High School, Room 264`.

### Change an event

Click (or tap) the event, then the pencil, change what you need, and **Save**. For a repeating
practice, Google asks whether to change **This event**, **This and following events** or **All
events**. Pick **This event** to move a single practice.

### Cancel or remove an event

Click the event, then the bin icon. For one missed practice in a series, choose **This event**.
Removing it from the calendar removes it from the website at the next update. There is no need to
post an announcement unless families need telling; if they do, post one as well.

## Announcements: the Website announcements sheet

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
the live website until the next update (see the next section), and the publishing policy promises
families a 24-hour clock.

## How long until changes appear

There are two places a change shows up, and they update on different clocks.

**On the website: when Charlie next publishes the site.** Today, the website is rebuilt and
published only when Charlie runs the publishing step by hand. There is no fixed schedule. If
something you added needs to be on the site by a certain time, or something needs to come off,
tell Charlie. A future update to the site (`v1-e37-t04`) makes the website check the calendar and
the sheet every hour and tell Charlie when there is something new to publish. Until the team's
cloud setup can publish on its own, Charlie still starts the final step, but it becomes one
command.

**In parents' own calendar apps: on that app's schedule, not ours.** Parents who subscribed to the
team calendar see your change directly from Google, whenever their calendar app next checks for
updates. Outlook checks about every three to six hours; Google Calendar and Apple's Calendar don't
publish a figure. Microsoft says it "can take more than 24 hours", and the same is true of the
others. Nobody on the team can make it faster. For anything urgent on a tournament day, contact families directly
instead of relying on the calendar.

## When something goes wrong

| What happened | What to do |
|---|---|
| You can't see the calendar or the sheet | Check you are signed in to the Google account Charlie shared with. If so, ask Charlie to share again |
| Your event is not on the website after an update | Open the event and check its calendar is **Whitefish Bay Debate**, not your own |
| Your announcement is not on the website after an update | Check its **Status** is `Publish`, its **Publish date** is today or earlier, and **Expires on** has not passed |
| Charlie says your announcement was rejected by the website check | The site refuses anything with an email address, a phone number, web code or a name that has not been checked. Fix the row; Charlie will say which rule it broke |
| Something about a student is on the site and should not be | Take it out of the calendar or sheet, **then phone or text Charlie straight away**. Do not wait for the next update |
| You made a mistake and want the old version back | In the sheet: **File, Version history, See version history**. In the calendar, re-enter the event. Or ask Charlie |

**Who to contact:** Charlie Clark, head coach, at charles.clark@wfbschools.com, or by phone or
text for anything urgent. If Charlie is unreachable and something about a student has to come down,
the second owner listed in
[website-content-accounts.md](../runbooks/website-content-accounts.md#owners) can do it.

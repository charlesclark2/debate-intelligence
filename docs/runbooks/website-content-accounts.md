# Runbook: website content accounts

> **Not in use.** ADR-0015 was revised before acceptance on 2026-10-01: events and announcements are
> files in `site/content/`, edited in git and deployed, so there is no team Google account and no
> CMS. The only external account behind the website's audience is the parent email list, covered by
> [parent-email-updates.md](../guides/parent-email-updates.md). What follows is the runbook written
> for the Google proposal, kept as the record in case a revisit trigger in
> [ADR-0015](../adr/0015-website-content-editing.md#decision-as-accepted) brings it back.

The one team-owned identity behind the website's editable content, what it owns, who can get into
it, how access is given and taken away, and how it is recovered when someone cannot get in or
leaves. Spec:
[`v1-e37-t01-content-editing-decision`](../../plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml).
Decision: [ADR-0015](../adr/0015-website-content-editing.md). The coaches' side:
[coach-website-editing.md](../guides/coach-website-editing.md).

**Every step here is run by the operator (Charlie), by hand.** An agent session never creates an
account, changes sharing, publishes a sheet or stores a secret. **No password, recovery code,
recovery phone number or secret address is ever written in this file or anywhere in the
repository.** This file records who and what, never how to get in.

## The team identity

One Google account, created for the team and belonging to no single coach, owns everything a coach
edits and everything a parent subscribes to. It was chosen by Charlie on 2026-09-29 over a
district role mailbox, because it can be created and controlled by the team today without waiting
on district IT.

| | |
|---|---|
| Account | A new Google account created for the team: **`<team account address>`** (filled in by the operator at [Step 1](#step-1--create-the-team-google-account)) |
| Belongs to | The Whitefish Bay debate team, not any coach. It is handed on, never closed, when a coach leaves. **Deleting the account deletes the calendar**, and every parent subscription with it |
| Sign-in protection | 2-Step Verification, with a passkey or security key for each owner |
| Owners | [Owners](#owners) below: at least two people, each able to sign in and to recover it alone |
| Where its password lives | In each owner's own password manager. Never in a shared document, an email or this repository |

### What it owns

| Resource | Used for | Visibility | Spec |
|---|---|---|---|
| **Whitefish Bay Debate** calendar | Every tournament, practice, meeting and deadline on the website and in parents' subscribed calendars | **Public**, "See all event details" | ADR-0015; rendered by `v1-e37-t02` |
| **Website announcements** sheet | The announcements on the home page and the news list | Private, shared with coaches. Only its **Published** tab is published to the web, as CSV | ADR-0015; read by `v1-e37-t03` |
| **The parent email list** (Buttondown) | Parent email updates | Private | `v1-e37-t05`, **still to be moved here**: see [Reconciling the parent email list](#reconciling-the-parent-email-list) |
| Test calendar and test sheet, while they exist | The ADR-0015 dry-run only. Deleted afterwards | Test calendar public; test sheet as the real one | ADR-0015 |

It owns nothing else. In particular it holds no student records, no media-consent forms, no
AWS access and no GitHub access: the site's code, hosting and deploys stay where
[team-website.md](team-website.md) puts them.

## Owners

"Owner" means a person who can sign in to the team account and recover it without help from anyone
else. The rule (ADR-0015, and the spec's ownership criterion) is **at least two owners at all
times**. If one leaves, a new second owner is added before the leaver's access is removed.

| Role | Person | Their own passkey or security key on the account | Can reset the password alone | Confirmed signed in on |
|---|---|---|---|---|
| First owner | Charlie Clark, head coach | `<yes/no>` | `<yes/no>` | `<date>` |
| **Second owner** | `<name and role, e.g. an assistant coach>` | `<yes/no>` | `<yes/no>` | `<date>` |

**Second owner status (2026-09-29): not yet named.** No second coach is available yet. Until
there is one, the account has one owner, and this runbook's continuity promise is not met. That is
recorded in the ADR-0015 session report as an open acceptance criterion, not treated as done.

Day-to-day, owners do not need to sign in as the team account. The calendar and the sheet are also
shared with each owner's **own** Google account at the highest level each allows ("Make changes
and manage sharing" on the calendar, Editor on the sheet), so either owner can add coaches, fix
content or take something down from their own login. Signing in as the team account is only
needed for ownership-level actions: deleting the calendar, changing what the sheet publishes, and
recovering the account.

## Coaches

| Coach | Calendar access | Sheet access | Added on | Removed on |
|---|---|---|---|---|
| `<first name, role>` | Make changes to events | Editor | `<date>` | |

Coaches use their own Google account, school or personal, whichever is on their phone. They never
sign in as the team account and never learn its password.

## Step 1 — Create the team Google account

**Operator steps** (about 15 minutes, in a browser)

1. Create a new Google account at [accounts.google.com](https://accounts.google.com/signup).
   Choose a name that says what it is and will still make sense after you stop coaching, for
   example one built from `wfbdebate`. Give the team's name, not a person's, as its name.
2. Security (**Manage your Google Account, Security**): turn on **2-Step Verification**, and add a
   **passkey** for your own device. Download the **backup codes** and store them in your password
   manager.
3. Recovery: set the recovery email to an address the **second owner** reads, and the recovery
   phone to yours. That way neither of you alone is a single point of failure.
4. Fill in `<team account address>` in [The team identity](#the-team-identity) and commit it. The
   address is not a secret; the password, codes and recovery phone are.

## Step 2 — Create the team calendar

**Operator steps** (about 10 minutes), signed in as the team account at
[calendar.google.com](https://calendar.google.com)

1. **Settings, Add calendar, Create new calendar.** Name: `Whitefish Bay Debate`. Description:
   `Tournaments, practices and team events. Public.` Time zone: **(GMT-05:00) Central Time -
   Chicago** (`America/Chicago`). **Create calendar.**
2. In that calendar's settings, **Access permissions for events**: tick **Make available to
   public**, and choose **See all event details**. (Anyone can read it, which is the point: the
   website and parents' calendar apps read it.)
3. **Share with specific people or groups**: add each owner's own Google account with **Make
   changes and manage sharing**, and each coach with **Make changes to events**. Nobody gets
   "See all event details" by invitation; public already covers reading.
4. **Integrate calendar**: copy the **Public address in iCal format**. It is public; it goes into
   the operator's environment and the CI secret store under the variable `v1-e37-t02` defines, not
   into git, because `v1-e37-t02` reads it only from the environment.
5. **Never copy the "Secret address in iCal format".** It shows every event including private
   ones, and anyone with it can read the calendar. If it is ever pasted anywhere, press **Reset**
   next to it straight away.

## Step 3 — Create the announcements sheet

**Operator steps** (about 20 minutes), signed in as the team account at
[sheets.google.com](https://sheets.google.com)

1. Create a spreadsheet named `Website announcements`. **File, Settings**: time zone
   **(GMT-05:00) Central Time - Chicago**.
2. Rename the first tab **Announcements** and put these headers in row 1, in this order:
   `Title`, `Publish date`, `Body`, `Expires on`, `Pin to top`, `Status`.
3. Validation (**Data, Data validation**):
   - `B2:B` and `D2:D`: **Is valid date**, reject input.
   - `E2:E`: **Checkbox**.
   - `F2:F`: **Dropdown**, options `Draft`, `Publish`, `Waiting for Charlie`, reject input.
4. **Format, Wrap text** on `C:C`, and freeze row 1 (**View, Freeze, 1 row**).
5. Add a second tab named **Published**. Put the same first five headers in row 1 (`Title` to
   `Pin to top`), then in `A2`:

   ```
   =IFERROR(FILTER(Announcements!A2:E, Announcements!F2:F="Publish"), "")
   ```

   Format `B:B` and `D:D` as **Format, Number, Custom date and time**, `yyyy-mm-dd`, so the
   published dates are unambiguous.
6. Protect the whole **Published** tab and row 1 of **Announcements** (**Data, Protect sheets and
   ranges**), editable by the owners only.
7. **Share**: each owner's own account as **Editor**; each coach as **Editor**. General access:
   **Restricted**.
8. **File, Share, Publish to web.** Link: choose the **Published** tab (not "Entire document") and
   **Comma-separated values (.csv)**. Under **Published content and settings**, choose the
   **Published** tab only and tick **Automatically republish when changes are made**. **Publish.**
   Copy the address and store it the same way as the calendar's (Step 2, point 4), under the
   variable `v1-e37-t03` defines.

What the published address exposes: exactly the rows a coach has set to `Publish`, which are the
rows the website is about to show anyway. Drafts, `Waiting for Charlie` rows and the Status column
never leave the sheet.

## Step 4 — Confirm

| Check | How | Expected |
|---|---|---|
| The calendar is public and readable without signing in | Open the public iCal address in a private browser window | A `.ics` file downloads or `BEGIN:VCALENDAR` shows |
| The sheet publishes only the Published tab | Open the CSV address in a private browser window | The five headers and only `Publish` rows. No `Status` column |
| Drafts stay private | Add a `Draft` row, wait five minutes, reload the CSV | The draft is not there |
| A guest's address does not reach the public feed | On the **test** calendar, add an event with a made-up guest address you own, then open the test calendar's public iCal address | The guest's address does not appear. If it does, record it in ADR-0015's dry-run section; the guide's "no guests" rule then carries more weight |
| Both owners can get in alone | Each owner signs in to the team account on their own device with their own passkey | Both succeed. Record the dates in [Owners](#owners) |
| Nothing secret is in the repository | `git grep -n -i -E 'calendar\.google\.com/calendar/ical/.*/private-|docs\.google\.com/spreadsheets/d/e/'` | No output |

Then fill in the tables above and commit.

## Giving a coach access

1. In the calendar's settings, **Share with specific people or groups**, add their Google account
   with **Make changes to events**.
2. In the sheet, **Share**, add the same account as **Editor**.
3. Send them [coach-website-editing.md](../guides/coach-website-editing.md). They need nothing else.
4. Add a row to [Coaches](#coaches).

## Removing a coach who leaves

The same day, from either owner's own account:

1. Remove them from the calendar's **Share with specific people or groups**.
2. Remove them from the sheet's **Share**.
3. Put the date in the **Removed on** column of [Coaches](#coaches).

Their past edits stay: events and announcements belong to the calendar and the sheet, not to the
person who typed them.

**If the person leaving is an owner**, add the new second owner first, then:

1. Sign in as the team account and **change its password**.
2. **Security, Passkeys and security keys**: remove theirs.
3. **Security, 2-Step Verification, Backup codes**: get new codes (the old ones stop working).
4. Update the recovery email or phone if it was theirs.
5. Remove their own account from the calendar and sheet sharing, and update [Owners](#owners).

## Recovery

| What happened | Recovery path |
|---|---|
| One owner forgot the password or lost their device | The other owner signs in and resets it, or the first owner uses a backup code from their password manager |
| Both owners' devices lost at once | Google's account recovery, using the recovery email (the second owner's) or the recovery phone (Charlie's) |
| Charlie stops coaching | The second owner becomes first owner, names a new second owner, and follows [Removing a coach who leaves](#removing-a-coach-who-leaves) for Charlie. This mirrors the site's own handover in the publishing policy, [Domains and continuity](../policies/website-publishing.md#domains-and-continuity) |
| Nobody who can sign in is left | The account cannot be recovered by the district, because it is not a district account. The calendar and sheet are recreated under a new team account from this runbook, and the website's two addresses are changed in the operator's environment. The public calendar's subscribers would have to subscribe again. This is the cost of choosing a team account over a district one, and it is why two owners is a rule, not a nicety |
| The account is compromised | Sign in, change the password, sign out all other sessions (**Security, Your devices**), check the calendar's and sheet's sharing lists, and look at the sheet's version history for edits nobody made. Tell the other owner |

## Secrets and addresses

| | What it is | Secret? | Where it lives |
|---|---|---|---|
| Calendar public iCal address | The public feed the website and parents read | No, but kept out of git so it can be changed without a code change | Operator environment and CI secret store, under the `v1-e37-t02` variable |
| Calendar **secret** iCal address | A private feed of everything | **Yes** | Nowhere. Never copied. Reset if exposed |
| Sheet published CSV address | The Published tab, public by design | No, handled like the calendar's | Operator environment and CI secret store, under the `v1-e37-t03` variable |
| Team account password, backup codes, recovery details | Getting in | **Yes** | Each owner's password manager only |
| A future webhook token or API key (`v1-e37-t04`) | Triggering or authenticating a rebuild | **Yes** | CI secret store and operator environment only, with a placeholder in `site/.env.example`. Owned by the team account where it is a Google credential |

**Changing an exposed address.** The calendar's secret address has a **Reset** button. A published
sheet address stays the same while the sheet stays published; to change it, stop publishing
(**File, Share, Publish to web, Stop publishing**), make a copy of the sheet, publish the copy and
update the environment variable.

## Reconciling the parent email list

`v1-e37-t05` set up the parent email list on Buttondown under **charles.clark@wfbschools.com**,
Charlie's own district address, with no second owner (`docs/guides/parent-email-updates.md`,
"Who owns the list", on that task's branch; not yet merged when this was written). ADR-0015 makes the team account above the single owner of every piece of website
content, and Charlie chose that identity knowing it would also cover the email list.

| | Today | Target |
|---|---|---|
| Buttondown login | charles.clark@wfbschools.com | The team account |
| Owners | Charlie only | The same two owners as above, through the team account's shared login (Buttondown's free plan has one login; separate logins need its paid Teams feature) |

To do, by the operator, after `v1-e37-t05` merges: change the Buttondown account's email to the
team account (Buttondown's documentation did not describe this when `v1-e37-t05` checked, so it may
need a request to their support), confirm the change from the team account's inbox, and update
this table and the email guide in the same pull request. Until then there are two ownership
stories, and this section says so.

## Test resources for the dry-run

For the ADR-0015 coach dry-run, the same account holds a **Whitefish Bay Debate (test)** calendar
and a **Website announcements (test)** sheet, built exactly as Steps 2 and 3 but with `(test)` in
the names. They carry no real student content. Delete both when the dry-run is recorded in the
ADR, and note the date here.

| Test resource | Created | Deleted |
|---|---|---|
| Whitefish Bay Debate (test) calendar | `<date>` | `<date>` |
| Website announcements (test) sheet | `<date>` | `<date>` |

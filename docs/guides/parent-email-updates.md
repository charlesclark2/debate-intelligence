<!-- docs-index: Parent email updates: the channel chosen and why, how a parent's address travels, who owns the list, how a coach sends an update and what may not go in one about students -->
# Parent email updates

How parents and guardians get team news by email, who owns the list, and how a coach sends an
update without putting a student at risk.

Spec: [`v1-e37-t05-parent-email-signup`](../../plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml).
Rules this follows: [`docs/policies/website-publishing.md`](../policies/website-publishing.md).

| | |
|---|---|
| Channel | **Buttondown**, a mailing service, on its free tier |
| Chosen by | Charlie Clark, head coach, 2026-09-29, from the comparison below |
| Activities director | Randee Drew, Athletics and Activities Director, **has been told and is fine with it** (as reported by Charlie on 2026-09-29) |
| List owner | **Interim:** the Buttondown account registered to **charles.clark@wfbschools.com**, a district account, with no second way in. **Moves to the team Google account (ADR-0015) as soon as that account exists**, with the start of the 2027-28 season as a backstop only. See [Who owns the list](#who-owns-the-list) |
| Signup page | The address in [`site/content/email-updates.json`](../../site/content/email-updates.json) (`signupUrl`) |
| Where it appears | "Email updates for parents and guardians" on the home page, under the tournament-schedule panel, and at the foot of the contact page |

## The channel, and why

### What was compared

The spec preferred the district's own parent messaging tool, because the district already owns
consent and lists for families. Two district routes were found, and four mailing services were
scored on what matters for a list of parents of minors. Every vendor fact below is from the
vendor's own pricing, help or legal pages, fetched on 2026-09-29; "unconfirmed" means the vendor's
pages did not say.

**District routes**

| Route | What was found | Why it was not used now |
|---|---|---|
| Skyward Family Access messages | The district's student information system. Families get logins from the district on registering, and Family Access carries "messages posted by the principal and teachers" (wfbschools.com, Family Access pages) | Enrolment-driven, not opt-in: it reaches families the district has on file, and whether a club can have its own group that parents choose to join is unconfirmed. A question for the activities office |
| Smore | The district and high school publish their family newsletters with Smore, and the district newsletter page has a "Subscribe to our list" form | Would mean a district Smore account for the team, which the activities office would have to grant; not available before the October 1 parent session |

**Mailing services** (free tier unless noted; cost is at the size of this team's parent list)

| | Buttondown | MailerLite | Mailchimp | Kit |
|---|---|---|---|---|
| Cost | $0 up to 100 subscribers, then about $9 a month | $0 up to 250 subscribers | $0 up to 250 contacts, but **500 sends a month**: four emails a month to more than 125 parents is over it | $0 up to 10,000 |
| Double opt-in | **Required by default** for every newsletter | On by default for forms | Available, off by default outside the EU, forms only | On by default for forms |
| One-click unsubscribe | Link in every email, but **it is two clicks**: it opens a page with an "Are you sure?" dialog and a "why are you unsubscribing?" survey (seen on this account, 2026-09-30). Every email also carries `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058, read from the test email's headers on 2026-09-30), so the Unsubscribe button mail apps show **is** one click | Yes, including the one-click header (RFC 8058) | Link in every email (two clicks); one click only through the header | Yes, header included; cannot be turned off |
| A second owner | Teams are Professional-plan only (+$79 a month) | **2 admin seats on the free plan** | 1 seat on free; about $13 a month for more | 1 user on free |
| Open and click tracking | **Both off by default**, both opt-in | On by default. Opens can be turned off; **clicks cannot** | On by default; on free, links are **always redirected** through Mailchimp | Open tracking on by default; no documented way to turn it off |
| Signup page with no script on our site | Hosted page, `https://buttondown.com/<username>` | Hosted form "share URL" | Hosted signup form URL | Hosted landing page |
| Emails published on the web | **Public archive by default**, can be set to Disabled (404) | No archive unless one is added | Public archive page created automatically, can be hidden | Per-email "public" setting |
| Vendor branding in emails | Yes, on free | Yes, logo on free | Yes, badge required on free | Yes, on free |
| Other | "We don't sell anything"; does not knowingly collect data from under-18s | | Terms allow using anonymised campaign content for Mailchimp's own marketing | New accounts are enrolled in the Creator Network recommendations by default |

### Why Buttondown

1. **Nothing about a parent is tracked unless someone turns it on.** It is the only service
   compared where both open and click tracking are off by default and can stay off. The spec asks
   for tracking disabled "where possible", and with MailerLite or Mailchimp it is not fully
   possible.
2. **Double opt-in cannot be skipped by accident**: it is the default for every signup.
3. **The signup is a plain page on Buttondown's own site**, so the team site links to it and loads
   nothing.
4. **Cost is $0 while the list is 100 or fewer**, and about $9 a month above that. Past 100
   subscribers someone has to pay or the list moves; see [When the list passes 100](#when-the-list-passes-100).

**The two things Buttondown does worse, written down so they are not forgotten:**

- **Its web archive of sent emails is public by default.** It is set to Disabled as part of
  setup (below), and that setting is part of the check before every send.
- **A second person with their own login costs $79 a month.** MailerLite is the only option that
  gives a second admin for free, but at the price of click tracking that cannot be turned off.
  Charlie chose Buttondown with that trade-off in view.

### Changing channel later

If the district offers its own tool, or the list outgrows Buttondown, the site side is two
fields in `site/content/email-updates.json` (`providerName` and `signupUrl`) and a deploy. No
code changes. The subscribers themselves do not move automatically: see
[Moving the list](#moving-the-list).

## How a parent's address travels

This is the first personal data the project has ever collected, so the path is written out in
full, including every place an address is seen by a person or a system.

```
parent's phone or browser
  │  1. taps "Sign up for email updates" on wfbdebate.com  (a plain link: nothing is sent to us)
  ▼
PROVIDER's hosted signup page  ── 2. parent types their address there, on the provider's site
  │
  ├─ 3. PROVIDER emails a confirmation link; nothing else is sent until the parent confirms
  ├─ 4. PROVIDER stores the address and sends each update
  └─ 5. list owners see the address in the PROVIDER dashboard
```

**What the team's systems never receive.** The website is static files with no form, no input
and no backend. The signup is a link; the browser leaves the site before the parent types anything,
so no request carrying an address ever reaches CloudFront, S3, AWS or this repository. This is
checked, not assumed:

| What | How it is checked |
|---|---|
| No page has anywhere to type an address | `site/tests/export/no-third-party-scripts.export-test.ts` parses every exported page and fails on any `form`, `input`, `textarea` or `select` |
| No provider script, pixel, iframe or form target on any page | The same suite fails on any element that fetches from another origin, and on any mention of a mailing provider's domain outside the one signup link, in HTML, inline scripts, page payloads and bundles |
| The link carries nothing about the visitor | `rel="noreferrer"`, and the site's `Referrer-Policy` is `strict-origin-when-cross-origin`: the provider is not even told which page the parent came from |
| No server-side record of the visit | CloudFront access logging is off for the site (ADR-0012 decision 8), and the two CloudFront functions log nothing |
| No workflow or infrastructure handles subscribers | No GitHub workflow and no Terraform resource refers to a mailing provider, and there is no email-sending, queue, database or compute resource in `infrastructure/` |

**Where an address does exist, named so nobody rounds it down:**

1. **At the provider.** That is the point: it stores the list and sends the emails. What it may
   do with the list is set by its terms, recorded in the comparison below.
2. **In front of the list owners.** Both owners can see every subscriber address in the provider's
   dashboard. That is the only place a coach looks at the list.
3. **In a coach's school mailbox, if a parent replies.** Updates are sent with a coach's
   `@wfbschools.com` address as the reply-to, so a reply lands in the district's email system like
   any other parent email.
4. **In the monthly subscriber export**, one CSV file kept in a private Drive folder so the list
   survives losing the account ([The monthly subscriber export](#the-monthly-subscriber-export)).
   Until the team account exists, that folder is in Charlie's district Google Drive.
5. **Nowhere else, by rule.** Addresses are never put in this repository, AWS or the site's
   content, never kept in any other spreadsheet or shared drive, and never sent anywhere as an
   attachment. A move to another provider is a direct export and import, and that file is deleted
   the same day.

## What may not go in an email about students

**The publishing policy governs every email, and this guide does not restate it.** Whatever
[`docs/policies/website-publishing.md`](../policies/website-publishing.md) allows or forbids about
a student on a page, it allows or forbids in an email, in the policy's own words:

| For | Read |
|---|---|
| Whether a student may be named, in what form, and checking the allowlist | [Students](../policies/website-publishing.md#students), including [The published-names allowlist](../policies/website-publishing.md#the-published-names-allowlist) |
| Contact details, places and times, quotes, sensitive matters | [Students](../policies/website-publishing.md#students) |
| Photographs | [Photos and media consent](../policies/website-publishing.md#photos-and-media-consent) |
| Results, records, rankings and opponents | [Results and awards](../policies/website-publishing.md#results-and-awards) |
| The check before anything goes out | [Pre-publication checklist](../policies/website-publishing.md#pre-publication-checklist), items 1 to 7 |

The rule for names is the site's rule because Charlie chose it on 2026-09-29, and the spec cites
the policy rather than copying it, so the email and the site cannot drift apart. If this guide and
the policy ever seem to disagree, the policy wins and this guide is wrong.

**What is different about email is the medium, not the rules:**

- **Every email is public.** Anyone can subscribe. Buttondown confirms that an address works, not
  that its owner is a parent.
- **An email cannot be taken back.** The policy's [Removal on request](../policies/website-publishing.md#removal-on-request)
  has nothing to act on once a message is in every subscriber's inbox. That includes a family who
  later withdraws consent. When in doubt, write at team level and link to the site.
- **Nothing checks an email automatically.** The site's build refuses an unreviewed name; an
  email has no build. The coach sending it goes through checklist items 1 to 7 by hand, against
  the allowlist in [`site/content/media-consent.yaml`](../../site/content/media-consent.yaml),
  every time.
- **No attachments and no embedded images.** An image sent in an email cannot be removed later.
  Link to the page on the site instead.
- **The list is for parents and guardians.** If a student subscribes, remove them. Students hear
  from the coaches through the team's own channels.

**Detail about individual students goes on the site, and the email links to it.** On the site, a
page passes the build guard and comes down on request; in an inbox, it does neither.

## How to send an update

Log in to Buttondown with the owner account (charles.clark@wfbschools.com).

1. **Write it.** On the **Emails** page, click **New**. Buttondown saves as you type. Give it a
   plain subject a parent can scan: "Tournament this weekend: bus times and what to pack".
2. **Keep it short and link to the site.** Dates, times, what to bring and what the team needs
   from families go in the email. Anything longer, and anything with a student's name in it, goes
   on the site as an announcement or a results page and the email links to it. Links to
   `https://wfbdebate.com/...` are fine; they are ordinary links, not tracked ones.
3. **Check it against the list below before sending.** Every item, every time.
4. **Preview it.** Click **Preview**, then **Send draft** to your own address. It arrives with
   `[PREVIEW]` in the subject. Read it on your phone, because that is where parents will.
5. **Send it.** Click **Publish**, check the summary in the "Send this email" drawer (it should say
   all subscribers), and click **Publish** again. Buttondown shows an **Undo** option for a short
   time afterwards if something is wrong. After that, the email cannot be recalled.

**Before every send:**

- [ ] **The policy's [pre-publication checklist](../policies/website-publishing.md#pre-publication-checklist), items 1 to 7**,
      gone through by hand for this email. Any "no" stops the send.
- [ ] **No attachment and no embedded image.** Link to the site instead.
- [ ] **Tracking is still off** (Settings: open and click tracking both off).
- [ ] **The archive is still Disabled** (Settings: Archives), so this email will not appear on the
      web.
- [ ] **Links go where they say** and point at the team site or another public page, never at a
      shared document with student information in it.

**Replies** come to charles.clark@wfbschools.com, the reply-to address set up on the account. A
parent's reply is ordinary district email and is handled like any other.

**Unsubscribes need nothing from a coach.** Every email ends with Buttondown's unsubscribe link.
It opens a page that asks "Are you sure?" and asks why they are leaving, so it takes two clicks,
not one. Mail apps such as Gmail and Apple Mail also show their own **Unsubscribe** button beside
the sender, and that one **is** one click: every email carries the RFC 8058 one-click headers
(`List-Unsubscribe-Post: List-Unsubscribe=One-Click`), and on 2026-09-30 clicking it unsubscribed
the test address in one click, showing as Unsubscribed in Buttondown almost immediately. A parent who asks a
coach to be taken off is removed from the subscriber list in Buttondown the same day.

**What not to send through this list:** anything urgent or safety-related on a tournament day. An
email to an opt-in list reaches only the parents who signed up and confirmed. Use the district's
channels and direct contact for those.

**Linking to the site's announcements.** When the site has announcements (`v1-e37-t03`), an update
can be a short summary with a link to the full announcement. The announcement passes the site's
build guard and can be corrected or taken down after publishing; the email cannot.

## Who owns the list

**The rule** (the spec's ac6, from 2026-09-30): at least two people can each, on their own, get
back into the list and its subscriber data, and that has been tried, not just written down. The
danger is not one person losing a seat. It is nobody being able to get in at all, and Buttondown's
password recovery runs through the mailbox the account is registered to. A paid second seat
($79 a month) would not fix that, so the team does not buy one.

**Today the list is in its interim state**: registered to Charlie's district address with no
second way in.

**When it moves: as soon as the team account exists.** The trigger is an event, not a date. The
team Google account that ADR-0015 names as the owner of the calendar, the announcements sheet and
this list is being set up by `v1-e37-t01`, and it is waiting for a second coach. **Moving this list
is part of setting that account up, not a later chore.** Whoever creates the account changes the
Buttondown login to it, in the same sitting where possible. The account is not finished until
this list is on it. Its owners and this move are recorded in
`docs/runbooks/website-content-accounts.md`.

**Backstop: the start of the 2027-28 season.** If the team account still does not exist by then,
that is the point to stop waiting and fix ownership another way: a district role mailbox, or the
district's own tool. The backstop is a deadline for giving up on the plan, not the plan. A parent
who asks who can delete their address is owed a shorter answer than "within the year".
(The PM set the trigger on 2026-09-30, replacing Charlie's date of the same day, which had made
the start of the 2027-28 season the target.)

| What ac6 asks for | Today (2026-09-30) | When it is met |
|---|---|---|
| Registered to the team identity | **No.** charles.clark@wfbschools.com, Charlie's district account | The Buttondown login is changed to the team Google account and confirmed from that inbox. Buttondown's docs do not describe changing the login address, so this starts with a request to its support |
| That mailbox reachable by two people | **No.** Only Charlie reads his district mailbox | The team account has two owners who can each sign in alone (the runbook's Owners table) |
| Credentials a second person can retrieve | **No.** Charlie only | The Buttondown password is kept the way the runbook keeps the team account's: in each owner's own password manager, never in a shared document, an email or this repository |
| The recovery path walked once by someone who is not Charlie | **Not yet** | The second owner signs out, resets the Buttondown password through the team inbox, signs in, and the date and their role are added below |
| A periodic subscriber export held by the team | **Started 2026-09-30, interim location** (see below) | Exports land in the team account's Drive instead of Charlie's |

Recovery walked: *not yet; record the date and the role of the person who did it here.*

### The monthly subscriber export

The export is what lets the list survive losing the Buttondown account entirely.

- **When:** on the first of each month, and before any change of owner or provider.
- **What:** Buttondown's subscriber export, as a CSV file. In Buttondown: **Subscribers**, then the
  **⋯** menu at the top right, then **Export**.
- **First taken:** 2026-09-30, by Charlie, into the interim location below.
- **Where, interim:** a private folder in Charlie's district Google Drive, shared with nobody. It is
  district-controlled, but only Charlie can reach it, so it does not meet "held by the team" on its
  own.
- **Where, target:** a private folder in the team Google account's Drive, shared only with that
  account's owners.
- **Only the latest file is kept.** Each month's export replaces the previous one, and the
  downloaded copy is deleted from the computer it was downloaded to.
- **Never** in this repository, AWS, the site, an email attachment, or anywhere else.

**If the account is ever lost and the list has to be rebuilt from an export:**
- Import only the people the export shows as subscribed.
- Anyone who unsubscribed after the export was taken cannot be known from it. So the first email
  after a rebuild says what happened and makes leaving the list the first thing in it.
- Parents were promised they could leave this list, and a rebuild must not quietly undo that.

### If the head coach stops coaching

The list goes with the team, not with the person, in the same spirit as the site itself (the
publishing policy, Domains and continuity). That means one of two things:
- the account moves to the team identity, if it has not already, and the incoming head coach
  becomes an owner of that identity; or
- the list is imported straight into the district's tool and the Buttondown account is deleted.

It is never left running unattended with parents still on it.

### When the list passes 100

Buttondown is free for the first 100 subscribers. Past that, either pay (about $9 a month; a
registered 501(c)(3) booster club, if the team has one, gets 50% off) or move the list. What
Buttondown does to a free list that crosses 100 was not confirmed from its docs, so check the
subscriber count before each season's first email and decide before it gets there.

### Moving the list

If the list moves to another provider or to the district's tool: export the subscribers from
Buttondown and import them directly into the new service in the same sitting, **delete that
migration file the same day** (the monthly export above stays the only standing copy), change the two fields in `site/content/email-updates.json`, deploy, and send
one last Buttondown email saying where updates now come from. Subscribers who confirmed with
Buttondown have confirmed a Buttondown list, so the new service should ask them to confirm again
unless the district's own consent already covers them.

## How the list was set up

The operator (Charlie) creates the account by hand; no agent session creates or touches it. The
settings that matter:

| Setting | Value | Why |
|---|---|---|
| Double opt-in | On (Buttondown's default) | Nobody receives team email without confirming from their own inbox |
| Open tracking | Off (Buttondown's default) | No pixel in any email |
| Click tracking | Off (Buttondown's default) | Links go straight to where they say |
| Archive | **Disabled**, so archive URLs return 404 | Emails are not published on the web |
| Reply-to | charles.clark@wfbschools.com | Replies stay in district email |
| Imports | None | Every subscriber signed up and confirmed themselves |

**Confirmed on the account by Charlie, 2026-09-29:** double opt-in on, open and click tracking
off, archive Disabled, no imports. The signup page is **`https://buttondown.com/wfbdebate`** and
lists no past emails.

**The archive redirects rather than returning 404.** Buttondown's docs say a Disabled archive
returns 404; on this account `https://buttondown.com/wfbdebate/archive` answers `302` to the
signup page (checked 2026-09-29, before any email was sent). Either way nothing is readable, but
because the behaviour differs from the docs, the test email was checked after it was sent
(2026-09-30): its archive address, `https://buttondown.com/wfbdebate/archive/test-update-please-ignore/`,
returns 404, and the newsletter's RSS feed, `https://buttondown.com/wfbdebate/rss`, carries no
emails at all, only the description.

## The site side

The site's part is one link. `site/content/email-updates.json` holds the provider's name, the
signup page address and the section's copy; `site/README.md` describes the fields. The section
appears on the home page, directly under the tournament-schedule panel, and at the foot of the contact page,
with the anchor `#email-updates`, so `https://wfbdebate.com/#email-updates` goes straight to it.

Content changes, including the signup address, reach parents only when the operator deploys:
`scripts/site_deploy.sh dev` for the preview, then `scripts/site_deploy.sh prod` from `main`
(see [`docs/runbooks/team-website.md`](../runbooks/team-website.md)).

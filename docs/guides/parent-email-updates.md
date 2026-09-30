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
| List owner | The Buttondown account registered to **charles.clark@wfbschools.com**, a district account. **No second owner yet**: see [Who owns the list](#who-owns-the-list) |
| Signup page | The address in [`site/content/email-updates.json`](../../site/content/email-updates.json) (`signupUrl`) |
| Where it appears | "Email updates for parents and guardians" on the home page, under the parent session, and at the foot of the contact page |

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
| One-click unsubscribe | Link in every email, plus the one-click `List-Unsubscribe` header | Yes, including the one-click header (RFC 8058) | Link in every email (two clicks); one click only through the header | Yes, header included; cannot be turned off |
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
| No page has anywhere to type an address | `site/tests/no-third-party-scripts.test.ts` parses every exported page and fails on any `form`, `input`, `textarea` or `select` |
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
   `@wfbschools.org` address as the reply-to, so a reply lands in the district's email system like
   any other parent email.
4. **Nowhere else, by rule.** The list is never exported into a spreadsheet, a shared drive, this
   repository, AWS or another service, and addresses are never copied into the site's content.
   If the list ever has to move to another provider, the move is a direct export from one
   provider and import into the other, and the exported file is deleted the same day.

## What may not go in an email about students

**Treat every email as public.** Anyone can subscribe: the provider confirms that an address
works, not that its owner is a parent. And unlike a page on the site, an email cannot be taken
back. The site's 24-hour removal promise has nothing to act on once a message is in every subscriber's inbox.
So every email meets **at least** the bar of the pre-publication checklist in the publishing
policy, and in places a higher one.

**Names follow the site's rules exactly** (Charlie's decision, 2026-09-29). A student is named in
an email only as the publishing policy allows on a page:

- in the published form **`FIRST NAME LAST NAME (GRADUATION YEAR)`**, for example
  "Jordan Rivera (2028)", or in the reduced form (first name only) that the family asked for;
- only if the student is on the published-names allowlist in
  [`site/content/media-consent.yaml`](../../site/content/media-consent.yaml) with a
  media-consent form **for the current season** confirmed with the activities office;
- **otherwise not at all.** Unknown is no. Write it at team level instead: "A Whitefish Bay Public
  Forum team reached quarterfinals."

The website's build checks names automatically; **an email has no such guard**, so the coach
sending it does that check by hand against the allowlist, every time. And because an email cannot
be recalled, a family who later withdraws consent cannot have their child's name taken out of an
email already sent. When in doubt, write at team level and link to the page on the site.

**Never, in any email, with or without consent:**

- **No student contact information.** No student email address, phone number, social media
  handle, messaging username, home address or bus route. Consent to publish a name is not consent
  to publish a way to reach a child (policy, Students 6). This includes a sign-up sheet or a
  carpool list pasted into the email.
- **No named student placed at a time and place.** Say when the bus leaves and where the team is
  staying; do not say which student is in which room, car or flight (Students 7).
- **Nothing sensitive about a named student.** No discipline, grades, health, disability,
  family circumstances or team-selection decisions (Students 9).
- **No records or rankings.** A single tournament placing is a result; a win-loss record, a
  speaker-point average or a ranking of team members is a profile (Results and awards 3 and 4).
- **No opponent students, ever** (Results and awards 5).
- **No student photographs.** An image attached to an email cannot be taken down. Link to the site
  instead, where a photograph is published under the media-consent rules and can be removed.
- **No student email addresses on the list.** The signup is for parents and guardians. If a
  student subscribes, remove them. Students hear from the coaches through the team's own channels.

**Where there is detail about individual students, put it on the site and link to it.** Results,
photographs and anything with a name in it belong on the site, where they pass the build guard and
can be taken down within 24 hours on request. The email says what happened in general terms and
links to the page.

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

- [ ] **No student contact information** of any kind, anywhere in the email.
- [ ] **Every named student is on the allowlist** with current-season consent, in their published
      or reduced form. Anyone else is written about at team level.
- [ ] **No named student is placed at a specific room, ride, hotel or arrival time.**
- [ ] **Nothing sensitive** about a named student, no records or rankings, no opponent students.
- [ ] **No student photograph** attached or embedded. Link to the site instead.
- [ ] **Tracking is still off** (Settings: open and click tracking both off).
- [ ] **The archive is still Disabled** (Settings: Archives), so this email will not appear on the
      web.
- [ ] **Links go where they say** and point at the team site or another public page, never at a
      shared document with student information in it.

**Replies** come to charles.clark@wfbschools.com, the reply-to address set up on the account. A
parent's reply is ordinary district email and is handled like any other.

**Unsubscribes need nothing from a coach.** Every email carries Buttondown's unsubscribe link and
the one-click unsubscribe header mail apps show as an "Unsubscribe" button. A parent who asks a
coach to be taken off is removed from the subscriber list in Buttondown the same day.

**What not to send through this list:** anything urgent or safety-related on a tournament day. An
email to an opt-in list reaches only the parents who signed up and confirmed. Use the district's
channels and direct contact for those.

**Linking to the site's announcements.** When the site has announcements (`v1-e37-t03`), an update
can be a short summary with a link to the full announcement. The announcement passes the site's
build guard and can be corrected or taken down after publishing; the email cannot.

## Who owns the list

| | |
|---|---|
| Account | Buttondown, registered to **charles.clark@wfbschools.com** |
| Why that address | It is a district account, not a personal one, so the district can recover access through its own email system if the head coach leaves |
| Second owner | **None yet.** Buttondown's Teams feature, which gives a second person their own login, is only on the Professional plan (+$79 a month). This is a known gap, recorded rather than hidden |
| Credentials | Held by the account owner only. Never in this repository, never in the site's content, never in a shared document. There is no API key |
| What the site holds | Only the public signup page address, in `site/content/email-updates.json` |

**Closing the second-owner gap** is a follow-up, and one of these closes it:

1. Move the account's login to a district role mailbox (for example a debate team address from
   district IT) that a second coach can also read. Buttondown's docs do not describe changing an
   account's login address, so this starts with a request to their support.
2. Pay for Teams if the budget allows, and invite a second coach as an admin.
3. Move the list to the district's own tool if the activities office offers one.

**If the head coach stops coaching**, the list goes with the team, not with the person, in the
same spirit as the site itself (publishing policy, Domains and continuity): the account is handed
to the incoming head coach or the activities office by changing its login to their district
address, or the list is exported straight into the district's tool and the account is deleted.
It is never left running unattended with parents still on it.

### When the list passes 100

Buttondown is free for the first 100 subscribers. Past that, either pay (about $9 a month; a
registered 501(c)(3) booster club, if the team has one, gets 50% off) or move the list. What
Buttondown does to a free list that crosses 100 was not confirmed from its docs, so check the
subscriber count before each season's first email and decide before it gets there.

### Moving the list

If the list moves to another provider or to the district's tool: export the subscribers from
Buttondown and import them directly into the new service in the same sitting, **delete the export
file the same day**, change the two fields in `site/content/email-updates.json`, deploy, and send
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
because the behaviour differs from the docs, the first real email's own web address was also
checked after sending: see the live check in the session report.

## The site side

The site's part is one link. `site/content/email-updates.json` holds the provider's name, the
signup page address and the section's copy; `site/README.md` describes the fields. The section
appears on the home page, directly under the parent session, and at the foot of the contact page,
with the anchor `#email-updates`, so `https://wfbdebate.com/#email-updates` goes straight to it.

Content changes, including the signup address, reach parents only when the operator deploys:
`scripts/site_deploy.sh dev` for the preview, then `scripts/site_deploy.sh prod` from `main`
(see [`docs/runbooks/team-website.md`](../runbooks/team-website.md)).

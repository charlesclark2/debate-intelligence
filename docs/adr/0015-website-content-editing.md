# ADR-0015: Coaches edit the website through a team Google Calendar and a Google Sheet

- Status: Proposed
- Date: 2026-09-29
- Deciders: Charlie Clark (head coach, product owner); a second coach's dry-run is required before
  this is Accepted
- Architecture references:
  - [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
  - [ADR-0012: Web hosting](0012-web-hosting.md), [ADR-0013: Two environments and dev→main promotion](0013-two-environments-and-dev-main-promotion.md)

## Context

The public team website ([ADR-0012](0012-web-hosting.md)) is a static export whose content lives in
`site/content/` as YAML and Markdown, edited in git and published by Charlie running
`scripts/site_deploy.sh`. That suits pages that change a few times a season. It does not suit
the two things epic E37 adds, which change weekly and need to be kept current by volunteer
assistant coaches who do not write code: **the tournament and practice schedule** and **short
announcements**. A site whose schedule only Charlie can update is a site whose schedule is out of
date by March.

What any answer has to fit:

- **The public site stays static.** No runtime server, database or API route
  ([ADR-0012](0012-web-hosting.md)), and the publishing policy forbids every third-party script,
  iframe and calendar embed ([Analytics and third parties](../policies/website-publishing.md#analytics-and-third-parties) 5,
  6, 8). External content can only enter at **build time**.
- **Students are minors.** The publishing policy governs every calendar entry and announcement,
  including its name rules, its 24-hour removal clock and its checklist item 16: an item naming a
  student needs Charlie's sign-off, an item naming nobody does not.
- **$0 at team scale**, and no trial that lapses into charges.
- **Ownership continuity.** Content and logins are owned by a team or district identity with at
  least two owners, never by one coach's personal account. The domains and the AWS account are
  already a single-person continuity risk
  ([Domains and continuity](../policies/website-publishing.md#domains-and-continuity)); this decision
  must not add a third.
- **Branch protection.** `protect-main` and `protect-dev` each require a pull request, with an empty
  bypass list ([branching-and-environments.md](../process/branching-and-environments.md)). Nothing,
  a content tool included, commits directly to either branch.
- **The district runs Google Workspace.** `wfbschools.com` has its MX records at Google (checked
  2026-09-29), so every coach has a Google login already.
- **`v1-e37-t05` is choosing the parent mailing service in parallel** under the same ownership rule.
  It chose Buttondown, registered to Charlie's own district address with no second owner. One team
  identity should own the calendar, the content source and the mailing list.

Vendor facts below were read from the vendors' own pages on 2026-09-29 (working agreement 7:
measure the source). They are cited in [References](#references).

## Criteria and weights

Charlie reviewed the fixed criteria on 2026-09-29, added two of his own, and chose the weights.

**Gates (pass or fail).** An option failing one is out, whatever it scores. Each is also on the
task's forbidden list.

| Gate | Passes when |
|---|---|
| $0 at team scale | Free for 2 to 5 editors, under 100 events and 100 announcements a year, with no trial that lapses into a charge |
| No student PII | The tool neither needs nor stores student names, contact details or photos beyond what the publishing policy allows on the site |
| Static-export fit | The site reads it at build time with no runtime backend, no embed and nothing loaded in a visitor's browser |

**Scored criteria**, 1 (poor) to 5 (excellent), weighted. Maximum 35.

| Criterion | Weight | What a 5 looks like | Added by |
|---|---|---|---|
| **Coach usability** without code or git | ×3 | A volunteer coach already knows the tool and adds an event in two minutes on a Sunday night with no new account | Spec |
| **Ownership continuity** | ×2 | Content and logins sit under a team identity with two owners, and nothing is lost when any one coach leaves | Spec |
| **Works on a phone** | ×1 | Adding or fixing an item from a phone at a tournament is as easy as on a laptop | Charlie |
| **Coach onboarding and offboarding** | ×1 | A new coach gets access in minutes with an account they already have; a leaving coach is removed in one step | Charlie |

Usability carries the most weight on purpose. Cost and elegance are easy to score. What decides
whether the site is still current in March is whether a volunteer uses the tool. A tool they will
not open on a Sunday night isn't cheaper than one that costs a little more. It just produces a
stale website.

## Options

Four options, as the spec requires. Google Calendar is scored as the events source. The other three
are scored as the announcements source, with a note on whether each could also carry events.

### Google Calendar (events)

A secondary calendar, **Whitefish Bay Debate**, owned by the team account and public at "See all
event details". Coaches edit it from their own Google accounts with "Make changes to events", on
the web or in the Calendar app. The build reads its **public iCal address** with no key. Parents
subscribe to the same address from Google, Apple or Outlook, which is epic E37's ac2 and which no
other option provides natively. The public address answered with no key when tested; the Calendar
API, by contrast, refused a keyless request, so the build uses the address, not the API. Structure
comes from conventions the guide teaches: a `Tournament: ` title prefix, all-day dates, and `Entry deadline:`, `Events:` and `Travel notes:` lines at the top
of the description. The weak point is validation. A mistyped line or an event saved to a coach's
own calendar is not caught by Google, so `v1-e37-t02` must be tolerant and warn.

### Git-backed CMS, Decap or Sveltia style (announcements)

An admin page edits Markdown in `site/content/` and commits it through the GitHub API. Every
editing coach needs **their own GitHub account with write access to the repository**, and signs in
through an OAuth flow that needs a separately hosted OAuth proxy (or, in Sveltia, a personal
access token pasted in and kept in the browser). Decap's own documentation says "all users must have
push access to your content repository". Decap's hosted sign-in, Turbo, removes the GitHub account
but is free for one seat. Sveltia describes itself as beta, and its editorial workflow had an open
bug report on 2026-09-16. The repository is `charlesclark2/debate-intelligence`: a personal GitHub
account, holding the platform's code and infrastructure as well as the site. Write access for
content is write access to all of that. The admin page's script is a third-party bundle and calls
`api.github.com` from the browser, so it cannot sit on the public site under the policy's
content-security rules without being self-hosted and given its own exception. And because both
long-lived branches refuse direct pushes, **every announcement becomes a pull request into `dev`
and then waits for a full dev→main promotion** before it can reach prod. Its strengths are real:
content is versioned and reviewed, and the existing build guard checks it exactly as it checks page
copy. They don't make up for asking a volunteer to open a GitHub account, and for a promotion per
announcement.

### Hosted headless CMS on a free tier (announcements)

A hosted editor such as Sanity, Contentful, Storyblok, Hygraph, DatoCMS or Prismic, with a proper
form per announcement: rich text, dates, drafts, and scheduled publishing. The build fetches
published entries through the vendor's API. It is the best editing experience of the four. Against
it: a new vendor login for every coach, a free-tier seat limit that decides how many coaches and
owners there can be, a read token to manage, an export format that is the vendor's own, and a free
tier that is the vendor's to change. It does nothing for events: a schedule kept in a CMS still needs
the site to generate its own feed, and parents' calendars would then update only when the site does.

The free tiers differ most on the one thing ownership needs, a second owner:

| Vendor | Free seats | A second owner free? | Free plan terms |
|---|---|---|---|
| **Sanity** | 20, Administrator and Viewer roles | Yes | "$0 forever"; 10,000 documents; public datasets only; webhooks included; Google sign-in |
| Contentful | 10 users | Yes | "$0 forever"; a hard API cap pauses delivery until the next month |
| Hygraph | 3 seats | Yes | "Free forever", described as for personal projects; 1,000 entries |
| DatoCMS | "2 editors" in one place, 1 collaborator in another | Unclear | Free; 300 records in total |
| Storyblok | 1 seat; a second is $15 a month | **No** | Described as for testing and personal projects |
| Prismic | 1 user | **No** | Described as for personal websites |

Sanity and Contentful both pass the "two owners at $0" test on a perpetual plan. Sanity is the one
scored below, because it signs editors in with Google and has no hard monthly cap that pauses
delivery. The rest either fail that test or describe their free tier as for personal projects,
which is not a basis for a team's site.

### Google Docs or Sheets (announcements)

A **Website announcements** sheet owned by the same team account, one row per announcement:
`Title`, `Publish date`, `Body`, `Expires on`, `Pin to top`, `Status` (`Draft`, `Publish`,
`Waiting for Charlie`). Dates are picked from a date picker, status from a dropdown, and pin is a
checkbox, so the structure that matters is validated by the sheet itself. A second, protected
**Published** tab holds a formula that shows only the `Publish` rows. **Only that tab is published
to the web as CSV**, so drafts and items awaiting Charlie never leave Google. The build reads that
CSV with no key. Every coach already has a Google login and has used a spreadsheet. The weak points
are a body typed into a cell, which is clumsy for long text on a phone, and the lack of a preview.
Publishing is Google's "Publish to the web" for a single tab, with "Automatically republish when
changes are made" on; Google says the update "might take a few minutes". A Workspace administrator
can turn publishing off, which is another reason the owner is a team account, not a district one.
Google Docs, one document per announcement, was considered and dropped within this option: its
export has no fields for dates, expiry or status, so structure would depend on conventions inside
prose.

## Scoring

Desk scores, 2026-09-29, before the coach dry-run. The dry-run confirms or corrects the usability
and phone scores of the options it tries, and the corrections are recorded in
[Dry-run](#dry-run).

| | Google Calendar (events) | Git-backed CMS | Hosted headless CMS | Google Sheets |
|---|---|---|---|---|
| **Gate:** $0 at team scale | Pass | Pass, narrowly. GitHub is free; the OAuth proxy's hosting cost is unconfirmed; Decap's hosted sign-in is free for one seat only | Pass for Sanity (20 seats, "$0 forever"); Storyblok and Prismic fail it on seats | Pass |
| **Gate:** No student PII | Pass. The guide forbids guests, attachments and names; `t02` strips addresses and numbers | Pass | Pass | Pass. The guide forbids names without Charlie; `t03` validates |
| **Gate:** Static-export fit | Pass. Public ICS read at build time | Pass for the site; the admin page needs its own hosting and an OAuth proxy | Pass. API read at build time; free-plan datasets are public, so no token is needed to read | Pass. Published CSV read at build time |
| Coach usability ×3 | **5**: already on every coach's phone | **2**: GitHub account, OAuth sign-in, and git concepts ("publish" is a commit that waits for a promotion) | **4**: the best editor, but a new tool and a new login | **4**: familiar, no new login; long text in a cell is clumsy |
| Ownership continuity ×2 | **4**: owned by the team account; two owners via the account and via "manage sharing" | **2**: content in a repository on a personal GitHub account | **3**: an organisation with two or more administrators, but a second vendor and a free tier that is the vendor's to change | **5**: the same team account as the calendar, one identity for both |
| Works on a phone ×1 | **5**: the Calendar app | **2**: a web admin page with a GitHub sign-in | **3**: mobile web editors, usable rather than good | **3**: the Sheets app works; long bodies are awkward |
| Onboarding and offboarding ×1 | **5**: share with the account a coach already has; unshare | **2**: a GitHub account, a collaborator invite to the whole code repository | **3**: an email invite to a new vendor account; seat-limited | **5**: share and unshare, as with the calendar |
| **Weighted total** (of 35) | **33** | **15** | **24** (Sanity) | **30** |

**Combinations**, because the decision is an events source and an announcements source:

| Combination | Identities a coach needs | Tools a coach learns | Score (events + announcements) |
|---|---|---|---|
| **Calendar + Sheets** | One (Google) | None new | 33 + 30 |
| Calendar + hosted headless CMS | Two (Google, the CMS) | One | 33 + 24 |
| Calendar + git-backed CMS | Two (Google, GitHub) | Two (GitHub, the CMS) | 33 + 15 |
| Everything in a CMS | One or two | One, and no calendar for parents | Fails epic E37 ac2 without a site-generated feed |

## Decision

**Events come from a public team Google Calendar. Announcements come from a Google Sheet. Both are
owned by one team Google account with at least two owners.** Page text stays where it is.

1. **Events source: the Whitefish Bay Debate Google Calendar**, a secondary calendar owned by the
   team account, public at "See all event details", time zone `America/Chicago`. Coaches edit it with
   "Make changes to events" from their own Google accounts. The site reads its **public iCal
   address** at build time (`v1-e37-t02`); parents subscribe to the same address. The **secret
   iCal address** is never copied anywhere and is reset if exposed. Event conventions are set by the
   [coach guide](../guides/coach-website-editing.md#events-the-team-calendar): a kind prefix on
   the title (`Tournament: `, `Practice: `, `Meeting: `, `Parent event: `, `Deadline: `), all-day
   tournaments, and `Entry deadline:` (month day, year), `Events:` (`PF`, `LD`, `Policy`) and
   `Travel notes:` lines at the top of the description. No guests, no attachments, no video-call
   links, and no student names on the calendar at all.
2. **Announcements source: the Website announcements Google Sheet**, owned by the team account,
   shared privately with coaches as Editors. The site reads only the **CSV of its protected Published
   tab**, which holds the rows whose Status is `Publish` (`v1-e37-t03`). A coach sets an item that
   names or pictures a student to `Waiting for Charlie`, and Charlie sets it to `Publish` after
   checking consent. That is checklist item 16 carried into the tool. Announcements carry **no
   images** from the sheet. A photograph goes to Charlie and into the repository with its
   media-consent manifest entry, as every photograph does now.
3. **Page text source: unchanged.** The site's pages stay in `site/content/`, edited in git and
   promoted under ADR-0013. They are structured, guarded by the build, and change a few times a
   season. Coaches ask Charlie. Revisit if a coach needs to edit page text often.
4. **One team identity.** A Google account created for the team (Charlie's choice, 2026-09-29, over
   a district role mailbox that would depend on district IT) owns the calendar and the sheet and is
   the target owner of `v1-e37-t05`'s parent email list. It has at least two owners, each able to
   sign in and recover it alone. The runbook defines it once:
   [website-content-accounts.md](../runbooks/website-content-accounts.md).
5. **Secrets never enter git.** Calendar API keys, CMS or Sheets tokens, OAuth client secrets and
   webhook secrets live only in the operator's environment and the CI secret store, with
   placeholders in `site/.env.example`. This decision needs **no secret at all** to read content:
   both addresses are public by design. They are still read from the environment rather than
   committed, so either can be changed without a code change. A secret appears only if a later task
   adds one (a webhook token in `v1-e37-t04`), and the same rule applies to it.
6. **All external content is fetched at build time, with a last-good fallback.** Every build fetches
   the calendar and the sheet. If a fetch fails, times out or returns something that does not parse,
   the build uses the last good snapshot, says so with the snapshot's age, and never fails a deploy
   or publishes an empty calendar because Google was unreachable. **A fallback may not undo a
   takedown.** A removal is complete only when the source is edited **and** a build has fetched
   successfully afterwards. A deploy made during a removal must not use a fallback snapshot. If it
   would, it stops and says so. `v1-e37-t02`, `t03` and `t04` implement this.
7. **Content-only edits do not go through git, so they do not go through ADR-0013's promotion.**
   A calendar or sheet edit changes no commit. It reaches the site when the site is next built and
   deployed from the commit already on `main`. Code, page text and anything under `site/content/`
   still go dev → promotion → main exactly as ADR-0013 says. Republishing for content is a rebuild
   of the same commit, deployed to dev, smoke-checked, and deployed to prod. It needs no pull
   request because nothing in git changed. Had a git-backed CMS been chosen, its commits would have
   had to land on `dev` through a pull request and wait for a promotion, since both branches refuse
   direct pushes. That is one of the reasons it was not chosen.

**How long until a change appears, today.** On the website: when Charlie next runs
`scripts/site_deploy.sh`, which is by hand and has no schedule. `v1-e37-t04` changes that. An
hourly check notices new content and asks Charlie to publish with one command, and publishing
becomes automatic only when the keyless deploy roles of `v2-e10-t03` exist. In parents' subscribed
calendars: whenever their calendar app next refreshes the feed. Google, Apple and Microsoft set that
interval, not the team (see [References](#references)).

**Revisit triggers.** A dry-run or a season of use shows coaches will not maintain the sheet
(consider a hosted CMS for announcements only; the calendar stays). Google changes public calendar or
publish-to-web behaviour. The district offers a role account that can own a public calendar (move
the identity to it). A coach needs to edit page text regularly.

## Dry-run

**Not yet run.** ADR-0015 stays Proposed until it is.

The spec requires a coach other than Charlie to try the prototype using only the
[coach guide](../guides/coach-website-editing.md), with no code, terminal or git. On 2026-09-29 no
second coach was available. The dry-run is scripted here so that whoever runs it records the same
things.

**The prototype.** The team account holds a **Whitefish Bay Debate (test)** calendar and a
**Website announcements (test)** sheet, built exactly as
[website-content-accounts.md](../runbooks/website-content-accounts.md) Steps 2 and 3 describe, with
no real student content. After the dry-run Charlie runs a throwaway checker outside this repository.
It reads the test calendar's public address and the test sheet's published CSV and lists what the
site would show and every entry the conventions could not read. That confirms the coach's entries
are machine-readable, not just saved.

**The script.** From a phone, or a laptop if the coach prefers, with only the guide open:

1. Add a two-day tournament with an entry deadline, the events entered and a travel note.
2. Post an announcement that should appear now.
3. Expire that announcement (set Expires on to yesterday, or Status to `Draft`).
4. Move one occurrence of a weekly practice (optional, if time allows).

**What to record.**

| | Result |
|---|---|
| Coach (role only, no name needed) | |
| Device (phone or laptop, which app) | |
| New account needed? (GitHub or otherwise) | |
| Time to add the tournament | |
| Time to post the announcement | |
| Time to expire it | |
| Where they got stuck, in their words | |
| Did the checker read every entry? | |
| Changes to the guide that followed | |
| Scores corrected by the dry-run | |

## Consequences

- **A coach needs one thing they already have, a Google login, and learns no new tool.** Onboarding
  is two shares, offboarding is two unshares, and neither touches GitHub or AWS.
- **Nothing to read content is secret.** A leaked address exposes only what is already public, and
  the secret iCal address is the one thing to keep out of everywhere.
- **Validation moves to the build.** Neither Google tool enforces the site's rules. The sheet
  enforces types and the status list, but not names or contact details, and the calendar enforces
  nothing. `v1-e37-t02` has to tolerate and warn on malformed events, and `v1-e37-t03`'s validator
  is the real guard for announcements. A coach learns about a rejected item from Charlie, not from
  the tool.
- **The website lags the calendar.** Parents who subscribe see an edit on their app's refresh cycle.
  The website sees it at the next publish, which today is manual. For urgent tournament-day changes,
  families are contacted directly, and the guide says so.
- **Charlie's sign-off is a status value, not a lock.** Any Editor can set `Publish`. It rests on the
  guide and on `v1-e37-t03`'s name check, which fails the build on an unchecked name either way.
  Protecting the Status column to owners only is possible, but it would slow down every item that
  names nobody, which the policy deliberately does not.
- **The calendar dies with the account.** Deleting a Google account deletes every calendar it owns,
  and only the owner can delete a secondary calendar. The team account is never closed while the
  calendar is in use; the runbook says so.
- **A team Google account is not district-owned.** If every owner is lost, the district cannot
  recover it. The calendar and sheet are recreated and parents re-subscribe. Two owners is therefore
  a rule. And `v1-e37-t05`'s list has to move to this account, which the runbook tracks.
- **Google is a dependency of the build, not of the site.** An outage delays an update; the
  last-good fallback keeps the site as it was.
- **Consequences for the later tasks.**
  - `v1-e37-t02` reads the public iCal address from the environment, parses the conventions above,
    and warns rather than fails on an event that breaks them.
  - `v1-e37-t03` builds its source adapter for the Published tab's CSV (columns `Title`,
    `Publish date`, `Body`, `Expires on`, `Pin to top`; dates `yyyy-mm-dd`). Bodies are plain text
    with blank-line paragraphs and bare URLs, with no Markdown and no images from the sheet.
  - `v1-e37-t04` has no webhook to receive. Neither Google tool sends one without a script, so its
    hourly schedule is the trigger, and its `site/content/**` push trigger covers page text.
  - `v1-e37-t05`'s mailing list moves under the team account (runbook,
    [Reconciling the parent email list](../runbooks/website-content-accounts.md#reconciling-the-parent-email-list)).
- **Exit plan if a free tier changes.** Both sources are Google consumer features with no paid
  tier involved. If publish-to-web or public calendars change, the sheet exports to CSV and the
  calendar to ICS in minutes, and the site's adapters (`t02`, `t03`) are the only code that changes.

## Alternatives considered

**Git-backed CMS (Decap or Sveltia).** Scored 15 of 35. Rejected mainly on coach usability and
onboarding. Every editing coach needs a GitHub account, collaborator access to a repository holding
the whole platform, and an OAuth flow backed by a proxy the team would host. On top of that, both
long-lived branches refuse direct pushes, so an announcement would wait for a dev→main promotion.
It would keep content versioned and reviewed in git, which is its real strength, and that is why
page text stays in git under Charlie.

**Hosted headless CMS on a free tier.** Sanity scored 24 of 35, second of the three announcement
options, and it has the best editor. Rejected because it adds a second
identity for every coach and a second ownership story, beside a calendar that has to be Google
anyway, for an editing gain on short announcements that the dry-run has not shown is needed. Most
other free tiers failed outright: one seat (Storyblok, Prismic), or plans their vendors describe as
for personal projects. It is the first thing to revisit if coaches will not maintain the sheet.

**Google Docs, one document per announcement.** Dropped within the Docs/Sheets option. A document
has no fields for publish date, expiry or status, so the build would parse conventions out of
prose, and a coach could not see at a glance what is live.

**A district role mailbox as the identity.** Recommended to Charlie as district-owned and
recoverable through IT. Charlie chose a team Google account instead, because it can be created and
controlled now. The vendor pages add two reasons: a Workspace administrator can limit external
calendar sharing to free/busy only and can turn off publish-to-web, either of which would break
this design; and a Workspace calendar can only be transferred to an owner in the same
organisation. If the district later offers a role account that can publish a public calendar,
moving the calendar and sheet to it is a revisit trigger.

**TinaCloud**, a git-backed editor whose hosted sign-in gives two free users by email with no
GitHub account. It removes the GitHub-account objection but not the branch one: its commits still
land in the repository and wait for a promotion, and its editorial workflow is on paid plans only.

**Everything in one CMS, events included.** Rejected. Parents' calendar subscriptions (epic E37 ac2)
would depend on the site generating its own feed, and they would update only when the site is
republished, rather than on each app's own refresh.

## References

- [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
- [ADR-0012: Web hosting](0012-web-hosting.md) (static export, no runtime backend);
  [ADR-0013: Two environments and dev→main promotion](0013-two-environments-and-dev-main-promotion.md);
  [branching-and-environments.md](../process/branching-and-environments.md) (the `protect-main` and
  `protect-dev` rulesets)
- [`docs/policies/website-publishing.md`](../policies/website-publishing.md): students, analytics
  and third parties, removal on request, pre-publication checklist item 16
- [`plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml),
  the task that owns this record; `t02` to `t05` in the same directory implement it
- [Coach guide](../guides/coach-website-editing.md) and
  [accounts runbook](../runbooks/website-content-accounts.md)
- Vendor pages read on 2026-09-29:

  - Google Calendar: [making a calendar public](https://support.google.com/calendar/answer/37083),
    [public and secret iCal addresses](https://support.google.com/calendar/answer/37648),
    [sharing permission levels](https://support.google.com/calendar/answer/37082),
    [transferring a calendar](https://support.google.com/calendar/answer/78739),
    [deleting a calendar](https://support.google.com/calendar/answer/37188),
    [Workspace calendar sharing controls](https://knowledge.workspace.google.com/admin/calendar/set-google-calendar-sharing-options).
    The public `basic.ics` address returned `text/calendar` with no key; the Calendar API returned
    403 for a keyless request (read-only requests, 2026-09-29).
  - Subscribed-calendar refresh: [Outlook.com and Outlook on the web](https://support.microsoft.com/en-us/outlook/import-or-subscribe-to-a-calendar-in-outlook-com-or-outlook-on-the-web)
    (about 3 and 6 hours, "can take more than 24 hours");
    [Google Calendar from URL](https://support.google.com/calendar/answer/37100) and
    [Apple Calendar](https://support.apple.com/guide/calendar/refresh-calendars-icl1024/mac) state
    no interval (unconfirmed).
  - Google Sheets: [publish to the web](https://support.google.com/docs/answer/183965) (single tab,
    automatic republish, "might take a few minutes", administrators can disable it).
  - Git-backed CMS: [Decap GitHub backend](https://decapcms.org/docs/github-backend/),
    [Decap Turbo](https://decapcms.org/turbo/),
    [Sveltia GitHub backend](https://sveltiacms.app/en/docs/backends/github),
    [Sveltia editorial workflow](https://sveltiacms.app/en/docs/workflows/editorial) and
    [issue 990](https://github.com/sveltia/sveltia-cms/issues/990),
    [TinaCloud pricing](https://tina.io/pricing).
  - Hosted headless CMS pricing: [Sanity](https://www.sanity.io/pricing),
    [Contentful](https://www.contentful.com/pricing/) (from the vendor's search listing; the page
    refused automated reads), [Hygraph](https://hygraph.com/pricing),
    [DatoCMS](https://www.datocms.com/pricing), [Storyblok](https://www.storyblok.com/pricing),
    [Prismic](https://prismic.io/pricing).
  - Not confirmed from any vendor page, and checked in the dry-run instead: whether a public
    calendar's feed carries guests' addresses. The guide forbids guests either way.

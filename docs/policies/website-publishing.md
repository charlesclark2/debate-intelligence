# Website publishing and student-privacy policy

| | |
|---|---|
| Policy version | 1.0 (draft) |
| Status | **Draft**, version 1.0, 2026-09-20. Not yet approved. See [Approval](#approval). |
| Owner | Charlie Clark (product owner and head coach) |
| Written by | v1-e36-t01-publishing-policy implementation session, 2026-09-20 |
| Applies to | Everything published on the public Whitefish Bay debate team website, in dev preview and in prod, and to every source the site is built from |
| Approved by | Not yet approved |
| Next review | Start of the 2027-28 season, or sooner if the district's conditions or media-consent process change |

This is the policy that governs everything published on the public Whitefish Bay debate team
website: the pages in [`site/`](../../site/), the calendar and announcements added by E37, and the
donation page added by E38. **It gates publishing anything about a student.** No page, photo,
announcement, calendar entry or donor line goes to prod until it has passed the
[Pre-publication checklist](#pre-publication-checklist).

It is not legal advice and it is not tax advice. Where a question needs the district, the school
or a lawyer to answer, this policy records it in [Open questions](#open-questions) rather than
guessing.

Two things make this policy different from an ordinary site style guide. First, **the people it
protects are minors**, and most of them are not the ones deciding what gets published. Second,
**the district, not this team, owns the rules**; the district's approval and its conditions are
recorded verbatim in [District approval and conditions](#district-approval-and-conditions), and
where this policy is stricter than the district requires, it says so and stays stricter.

## Scope

**In scope**

- Every page of the public team website, in both environments: the dev preview distribution and
  the prod distribution (`v1-e36-t02`).
- Every file the site is built from: `site/content/`, `site/config/`, `site/public/` and any
  content source a later task adds (a hosted CMS, a sheet, a calendar feed).
- Everything E37 adds: the events calendar, announcements, and the parent email-updates signup.
- Everything E38 adds: the donation page and the opt-in donor recognition section.
- Anything else served from the team domain before the V2 authenticated app exists.

**Out of scope**

- The V2 authenticated application in `web/`, its accounts and its uploads. Those are covered by
  [ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md), the architecture proposal
  §14, and the `v2-e35` gates in
  [caselist-data-use.md](caselist-data-use.md#v2-e35--debate-tub-v21). When the V2 app mounts under
  the same domain, this policy still governs the public pages beside it.
- Evidence, disclosures and camp files, which are covered by
  [caselist-data-use.md](caselist-data-use.md).
- Hosting, TLS, security headers and deploy mechanics (`v1-e36-t02`, `v1-e36-t05`).
- The district's own website, the school's social media accounts, and anything a tournament,
  Tabroom or the National Speech and Debate Association publishes. This policy cannot reach them;
  [Removal on request](#removal-on-request) says so to requesters.

**Who this binds.** Everyone who can put content on the site: Charlie, any assistant coach given
editing access under ADR-0015 (`v1-e37-t01`), the operator who runs deploys, and every
implementation session that writes page copy.

## District approval and conditions

> **Pending Charlie's record of the approval.** The approval has been given; the approver's role,
> the date, the conditions attached and where the written record is kept are supplied by Charlie
> and recorded verbatim below before this policy can be approved. This is
> [open question 1](#open-questions), and it blocks the [Approval](#approval) section.
> Nothing in this section is written by an implementation session from inference.

**Where the written approval lives.** _To be recorded: Charlie names the channel (email thread,
meeting minute, signed form) and where he keeps it. The record itself is **not** committed to this
repository._

### Conditions attached by the district

Each condition is recorded in the district's own words. A condition that is paraphrased says so.
Nothing is added, softened, or inferred from what a district "would probably want"; anything not
yet known is an [open question](#open-questions), not a guess.

| # | Condition, as the district stated it | Where this policy implements it |
|---|---|---|
| _1_ | _To be recorded from Charlie's account of the approval._ | |

**If the district's conditions and this policy disagree, the district wins** where the district is
stricter, and this policy wins where this policy is stricter. This policy is deliberately
stricter than the district requires in at least one place today; see
[Students](#students).

**If a condition changes**, publishing of the affected content stops until this policy is revised
and re-approved under [Review and change control](#review-and-change-control).

## Students

Every current student on this team is presumed to be a minor. The rules below apply to all of
them, on every page, in every announcement, in every calendar entry, in every image caption and in
every file name.

### Consent tiers

What may be published about a student depends only on what consent is on file for that student
through the district's media-consent process ([Photos and media consent](#photos-and-media-consent)).
There are three tiers and no others.

| Tier | Consent on file | What may be published |
|---|---|---|
| **Full** | The district's media-consent form completed and not withdrawn, covering name and likeness | Full name and graduation year, as the district's rule allows; photographs; quotes attributed by name |
| **Limited** | Consent on file that excludes name, likeness or both, or a family that asked for less | First name only, and only for what the family agreed to. No photograph unless likeness is separately covered |
| **None** | No consent on file, consent withdrawn, or consent status unknown | **No name, no photograph, no quote, no identifying detail of any kind.** The student appears only inside a team-level statement that names nobody |

**Unknown is None.** A student whose consent status cannot be confirmed is treated as tier None.
The site never publishes on the assumption that consent probably exists.

**Consent is withdrawable at any time, by the student or by a parent or guardian, without giving a
reason.** Withdrawal moves the student to tier None and triggers
[Removal on request](#removal-on-request).

### Rules

1. **Never a surname without Full consent.** A surname may appear only for a tier-Full student.
   There is no "first name plus last initial" form; it is either the full name under Full consent,
   the first name under Limited consent, or no name.
2. **Graduation year travels with the name, and only with the name.** Where the district's rule
   requires a graduation year beside a published student name, it is written as a class year
   ("Class of 2028"). A graduation year is never published beside anything less than a name it is
   already attached to, and **age, date of birth, grade level and birthday are never published at
   all**.
3. **No student contact details, ever, at any tier.** No student email address, phone number,
   social media handle, messaging username, gamer tag, home address, home town beyond
   "Whitefish Bay", bus route, or personal website. This rule has no consent exception: consent to
   publish a name is not consent to publish a way to reach a child.
4. **No routine location or schedule that places a named student at a time and place.** The site
   may say when and where the team practices and which tournaments the team attends. It may not
   pair a named student with a specific room, ride, hotel, arrival time or solo travel plan.
5. **No student may be quoted at tier None or attributed at tier Limited beyond a first name.** A
   quote is a publication about that student like any other.
6. **No student writes their own exception.** A student asking to have their full name or photo on
   the site does not change their tier; only the district's consent record does.
7. **Nothing sensitive, at any tier.** No disciplinary matter, no grade or academic record, no
   Individualized Education Program or Section 504 information, no health or disability
   information, no family circumstance, no immigration status, no free-or-reduced-lunch status, no
   team-selection or cut decision about a named student. Where the line is unclear, the content
   does not publish and Charlie decides.
8. **Former students are not automatically free.** An alum's name stays at the tier it was
   published under. An alum who asks to be removed is removed under
   [Removal on request](#removal-on-request), the same as a current student.
9. **No student names in the site's own machinery.** Image file names, alt text file paths,
   commit messages, build logs and CI output carry no student name; see
   [Photos and media consent](#photos-and-media-consent) for how consent is referenced instead.
10. **No student names in this repository outside published content.** Test fixtures, examples and
    documentation (including this policy) use invented names. A student name reaches the
    repository only inside `site/content/` or the published-names allowlist below, which is to say
    only where it is already public on the site.

### The published-names allowlist

Because the build has to be able to check rules 1 and 2 mechanically, the names the site is
permitted to print live in one reviewed list rather than being spread through the copy.

- The list holds every name the site may publish: coaches and other adults, the school, opponent
  schools, tournaments, and those students at tier Full or Limited.
- Each student entry carries the name in its permitted form, the tier, the graduation year where
  one is published, and the opaque consent reference from
  [Photos and media consent](#photos-and-media-consent). It carries no contact detail and no
  document.
- **Everything in the list is already public by construction**: an entry exists only so that the
  same name can appear on a public page. Nothing is learned from the list that the site does not
  already say.
- A build fails when content contains a "First Last" name that is not in the list
  (`v1-e37-t03` acceptance criterion 3). **Removing an entry and republishing is how a name comes
  off the site**, which makes [Removal on request](#removal-on-request) a content edit rather than
  a code change.
- Charlie owns the list. A coach adds an entry only after confirming the consent record; the
  consent records themselves stay with the district and with Charlie, outside this repository.

`v1-e36-t04` builds the checks; this policy sets what they check.

## Photos and media consent

1. **A student photograph publishes only under the district's media-consent process**, for a
   student at tier Full whose consent covers likeness. No other basis counts: not a parent's
   verbal "sure", not a photo the student posted themselves, not a photo a tournament published,
   not a photo already on the district's own site.
2. **A family that has opted out is never depicted**, including in a group shot they happen to
   stand in. If one student in a photograph lacks consent, the photograph does not publish. It is
   not cropped "closely enough", blurred, or published small.
3. **Consent is recorded as an opaque reference, never as a student record in the repository.**
   Every image of an identifiable person carries an entry in the media-consent manifest
   (`v1-e36-t04` acceptance criterion 3) holding:

   | Field | Example | Notes |
   |---|---|---|
   | Image path | `public/photos/novice-orientation-2026.jpg` | |
   | Consent reference | `MC-2026-014` | Opaque. Points at the written consent Charlie holds outside the platform |
   | Who is depicted | `2 team members, both covered` | Counts and coverage, **no names** |
   | Date approved | `2026-09-18` | |

   The mapping from a reference to a student is Charlie's, kept with the district's records and
   **not committed**. A build fails on any image of a person with no manifest entry.
4. **No photograph of an identifiable student who is not on the team**, and no photograph of
   another school's students, whoever took it.
5. **Metadata is stripped before publication.** Every image is exported without EXIF data:
   no GPS coordinates, no device identifier, no original file name, no capture timestamp.
6. **Captions and alt text follow [Students](#students).** Alt text describes what is in the
   picture and names a student only at the tier that student's name may be published at; "a
   debater at the podium" is the default.
7. **Video and audio are treated as photographs**, with the same consent requirement, plus
   captions as required by [Accessibility](#accessibility). Nothing is embedded from a
   third-party video host; see [Analytics and third parties](#analytics-and-third-parties).
8. **Safe-by-default alternatives always exist** and are preferred when consent is uncertain:
   wide shots with no recognizable face, an empty competition room, a flight schedule on a
   whiteboard, trophies, the team's own graphics.
9. **Screenshots count.** A ballot, a Tabroom bracket, a pairing sheet or a group-chat screenshot
   is a publication of every name on it, and is subject to every rule above. In practice these do
   not publish.

## Results and awards

Results are the reason most families visit the site, and they are also the content most likely to
name a child. Both facts are respected here.

1. **The district's form is the published form**, for students at tier Full:
   - **Individual events** (Lincoln-Douglas debate, and any speech event the team enters) are
     published as full name, graduation year, event, tournament and placing, for example
     "Jordan Rivera, Class of 2028, Lincoln-Douglas debate, quarterfinalist".
   - **Partner events** (Policy debate, Public Forum debate) name **both** partners with both
     graduation years; a partnership is never published with one half named.
2. **Every named student in a result must be tier Full and on the
   [allowlist](#the-published-names-allowlist).** If either partner is not, the result publishes in
   team-level form instead:

   > "A Whitefish Bay Public Forum team reached quarterfinals at the Marquette tournament."

   The team-level form is always available and is never treated as a lesser outcome to be
   apologized for on the page.
3. **No record, ranking or rating of a student over time.** No win-loss record, no season points
   total, no speaker-point average, no bid count, no leaderboard, no "most improved" table, and no
   ranking of team members against one another. A single tournament placing is a result; an
   accumulated record is a profile, and profiles of minors do not publish.
4. **Nothing about losing.** A result naming a student is published only where the student placed
   or advanced. The site does not publish elimination-round losses by name, records with losses in
   them, or a list of who did not break.
5. **No opponent students are named**, in any form, ever. Opponent *schools* may be named; the
   students debating for them may not.
6. **No ballots, no round-by-round detail, no reason for decision, no judge names beyond adults
   acting in a public judging capacity**, and no critique of a student's performance.
7. **Results are facts Charlie supplies**, taken from the tournament's own published results. An
   implementation session never invents, estimates or reconstructs a result.
8. **A result comes down on request like anything else**, and a student moving to tier None takes
   their name out of every past result, which then reverts to team-level form rather than being
   deleted outright.

## Removal on request

**Anything on this site comes down on request, without the requester having to justify it, and
without argument.** This is the rule a parent is most likely to need and the one most likely to be
tested on a weekend.

**Who may ask**

- Any student on the team, about themselves. A student does not need a parent's backing to have
  their own name or photo taken down.
- Any parent or guardian, about their child.
- The district, the high school administration or the activities director, about anything.
- Any adult named on the site, about themselves.
- Any donor listed under E38's recognition section, about their own entry.
- A coach, about anything published in error or outside this policy.

**How to ask.** Through the contact channel published on the site's Contact page (`v1-e36-t04`),
or directly to Charlie. The request names the page, the photo or the person; **no reason is
required and none is weighed.** Charlie confirms the requester's standing only where the request
concerns someone other than the requester.

**How fast**

| Step | Within | Who |
|---|---|---|
| Acknowledge the request | Same day | Charlie, or the coach who received it |
| Content removed from **prod**: content edited or the allowlist entry deleted, `site/` rebuilt, deployed, **and a CloudFront invalidation issued for the affected paths** (`/*` when in doubt) | **24 hours of the request** | Charlie, or a coach with deploy access, running `scripts/site_deploy.sh` (`v1-e36-t05`) |
| Content removed from the **dev preview** and from the content source (CMS, sheet or `site/content/`) so the next build cannot restore it | Same run, before prod is redeployed | The same person |
| Written confirmation to the requester, naming what was removed and when | With the removal, inside the same 24 hours | Charlie |

**The invalidation is not optional.** A CloudFront edge cache will keep serving a removed page or
image after the bucket has been updated. A removal is not complete until the invalidation has
completed and the person doing it has loaded the affected URLs and seen the content gone.

**What removal does**

- Deletes or rewrites the content in `site/content/` (or the E37 content source), so the next
  scheduled rebuild cannot bring it back.
- Removes the person's entry from the [published-names allowlist](#the-published-names-allowlist),
  which makes any remaining mention of that name **fail the build** rather than republish.
- Deletes the image and its media-consent manifest entry, for a photo request.
- Rewrites an affected result into its team-level form rather than deleting the team's result
  outright, unless the requester asks for the whole item to go.
- Is recorded in a removal log holding the date, what was removed by page and path, the requester's
  standing (student / parent / district / adult / donor), the consent reference where one applies,
  and the invalidation id. **The log holds no student name and is not committed to this
  repository.**

**What removal does not do**

- It does not reach the district's site, the school's social accounts, a tournament's results
  page, Tabroom, or a search engine's cache. The requester is told this plainly and, where it
  helps, told who to ask. Charlie may additionally request removal from a search engine's cache;
  this policy does not promise a result that is not the team's to give.
- It does not reach a copy someone else already downloaded.
- It does not require the requester to explain themselves, now or later.

**Standing rule: when in doubt, take it down first and discuss afterwards.** Nothing on this site
is worth leaving up over an unresolved objection from a family.

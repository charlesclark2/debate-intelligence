# Website publishing and student-privacy policy

| | |
|---|---|
| Policy version | 1.0 |
| Status | **Draft**, version 1.0, 2026-09-20. Awaiting Charlie's approval; see [Approval](#approval). |
| Owner | Charlie Clark (product owner and head coach) |
| Written by | v1-e36-t01-publishing-policy implementation session, 2026-09-20 |
| Applies to | Everything published on the public Whitefish Bay debate team website at `wfbdebate.org`, in the dev preview and in prod, and every source the site is built from |
| Approved by | _Not yet approved_ |
| Next review | Start of the 2027-28 season, or sooner if the district's conditions, the media-consent process, or domain ownership change |

This is the policy that governs everything published on the public Whitefish Bay debate team
website: the pages in [`site/`](../../site/), the calendar and announcements added by E37, and the
donation page added by E38. **It gates publishing anything about a student.** No page, photo,
announcement, calendar entry or donor line reaches prod until it has passed the
[Pre-publication checklist](#pre-publication-checklist).

It is not legal advice and it is not tax advice. Where a question needs the district, the school
or a lawyer to answer, this policy records it in [Open questions](#open-questions) rather than
guessing.

Two things make this policy different from an ordinary site style guide. First, **the people it
protects are minors**, and most of them are not the ones deciding what gets published. Second,
**the district, not this team, owns the rules about students and about the school's name**; the
approval and any conditions attached to it are recorded in
[District approval and conditions](#district-approval-and-conditions) as the activities director
gave them.

## Scope

**In scope**

- Every page of the public team website, in both environments: the dev preview distribution and
  the prod distribution at `wfbdebate.org` (`v1-e36-t02`).
- Every file the site is built from: `site/content/`, `site/config/`, `site/public/`, and any
  content source a later task adds (a hosted content management system, a sheet, a calendar feed).
- Everything E37 adds: the events calendar, announcements, and the parent email-updates signup.
- Everything E38 adds: the donation page and the opt-in donor recognition section.
- Anything else served from the team's domains before the V2 authenticated application exists.

**Out of scope, and covered elsewhere.** These are cross-referenced, not restated here; where a
rule below touches one of them, the other document governs its own subject.

| Subject | Where it lives |
|---|---|
| Disclosed evidence, OpenCaselist and OpenEv camp files | [`docs/policies/caselist-data-use.md`](caselist-data-use.md) |
| The district's donation process, the approved payment destination, receipts and donor opt-in wording | `docs/policies/donations.md` (`v1-e38-t01`), not yet written |
| The V2 authenticated application in `web/`, its accounts, uploads and the debate tub | Architecture proposal §14, [ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md), and the `v2-e35` gates in [caselist-data-use.md](caselist-data-use.md#v2-e35--debate-tub-v21). When the V2 app mounts under the same domain, this policy still governs the public pages beside it |
| Hosting, TLS, security headers, deploys and cache invalidation mechanics | `v1-e36-t02`, `v1-e36-t05`, ADR-0012 |
| The district's own website, the school's social media accounts, and anything a tournament, Tabroom or the National Speech and Debate Association publishes | Not ours. This policy cannot reach them, and [Removal on request](#removal-on-request) says so to requesters |

**Who this binds.** Everyone who can put content on the site: Charlie, any assistant coach given
editing access under ADR-0015 (`v1-e37-t01`), the operator who runs deploys, and every
implementation session that writes page copy.

## District approval and conditions

The approval below is recorded as the activities director gave it. An implementation session never
infers, extends or softens it.

| Field | Value |
|---|---|
| Approved by | **Randee Drew, Athletics and Activities Director, Whitefish Bay High School** |
| Approval date | **2026-09-18** |
| What was approved | A public website for the debate team |
| Conditions attached | **None stated.** The activities director attached no conditions to the approval |
| How the site must describe itself | **"A team-run site for Whitefish Bay debate."** The site presents itself as the team's, not as an official district communication |
| Media consent | **The team has students sign consent forms, which are maintained by the activities office.** Photographs publish only against a form on file there; see [Photos and media consent](#photos-and-media-consent) |
| Where the written record is kept | Charlie's record of the approval. **Not committed to this repository** |

**"None stated" is recorded as a fact, not read as permission.** The district attaching no
conditions does not make this policy's rules optional; it means every rule below is the team's own
choice, adopted because the subjects are minors. In particular the rules on
[Students](#students), [Results and awards](#results-and-awards),
[Analytics and third parties](#analytics-and-third-parties) and
[Removal on request](#removal-on-request) are stricter than anything the district asked for, and
they stay that way unless this policy is revised and re-approved.

**If the district later states a condition**, it is added to this section verbatim and the policy
version is bumped. Where a district condition is stricter than a rule here, the district's
condition governs and publishing of the affected content stops until this policy is revised. Where
this policy is stricter, this policy governs.

## Domains and continuity

`wfbdebate.org` is the public site. `wfbdebate.com` redirects to it and serves no content of its
own; every rule in this policy applies to whatever either name resolves to.

| | |
|---|---|
| Registrant of both domains | **Charlie Clark, personally. Not the district.** |
| Who renews them | Charlie, at his own expense, from his own registrar account |
| What the district owns | The approval, the school's name and marks, and the media-consent records. Not the domains, not the AWS account, not the site's content |

This is the site's single largest continuity risk and is written down rather than left implicit.

1. **Auto-renewal is on for both domains**, and the registrar account's contact address is one
   Charlie will still read after he stops coaching. A lapsed domain does not merely take the site
   down; it lets someone else register a name that parents associate with the school.
2. **If Charlie stops coaching, or at his request at any time, both domains, the AWS account that
   serves them and the content repository are offered to the district or to the incoming head
   coach**, at no charge, as a transfer. The site is not handed to a successor informally while
   the registration stays in a former coach's name.
3. **If no successor takes them**, the site is taken down and both domains are allowed to expire
   or are parked with no content, rather than left running unmaintained. An unmaintained site
   still naming students is a live obligation nobody is meeting.
4. **A takedown under 3 removes content, not just DNS.** Objects are deleted from the prod bucket
   and a CloudFront invalidation is issued, because pointing a domain elsewhere leaves the content
   reachable at its distribution URL.
5. **At least one other person can reach the site's controls.** Charlie names a second coach or
   district contact who can take the site down if Charlie is unavailable, and records how. This is
   [open question 2](#open-questions).

## Students

Every current student on this team is presumed to be a minor. The rules below apply on every page,
in every announcement, in every calendar entry, in every image caption and in every file name.

### What may be published about a student

| | Default | Requires | Never |
|---|---|---|---|
| **Name** | **First name, last name and graduation year** | Nothing beyond the student being a team member | Any name at all, once the student or their family has asked for less; see rule 2 |
| **Photograph or video** | Not published | **A district media-consent form on file with the activities office**, covering that student, not withdrawn | A student with no form on file, or whose family opted out |
| **Contact details** | Not published | — | **Always never. No consent makes these publishable** |

1. **Full name and graduation year is the published form.** A student name appears as first name,
   last name and class year, for example "Jordan Rivera, Class of 2028". The graduation year is
   written as a class year and travels only beside a name; **age, date of birth, grade level and
   birthday are never published at all**, with or without a name.
2. **Any student, parent or guardian may ask for less, at any time, without giving a reason, and
   it is honored.** The choices are first name only, or no name at all. The request is recorded in
   the [published-names allowlist](#the-published-names-allowlist) and takes effect on the next
   deploy under [Removal on request](#removal-on-request). Nobody is asked to justify the request
   and nobody is talked out of it.
3. **No student contact details, ever.** No student email address, phone number, social media
   handle, messaging username, home address, home town beyond "Whitefish Bay", bus route or
   personal website. This rule has no exception: consent to publish a name is not consent to
   publish a way to reach a child.
4. **No photograph without a form on file.** A student photograph publishes only under the
   district's media-consent process; see [Photos and media consent](#photos-and-media-consent).
   Unknown consent status is treated as no consent.
5. **No routine location or schedule that places a named student at a time and place.** The site
   may say when and where the team practices and which tournaments the team attends. It may not
   pair a named student with a specific room, ride, hotel, arrival time or solo travel plan.
6. **A quote is a publication about the student who said it**, and follows the same name rule as
   anything else.
7. **Nothing sensitive, ever.** No disciplinary matter, no grade or academic record, no
   Individualized Education Program or Section 504 information, no health or disability
   information, no family circumstance, no immigration status, no free-or-reduced-lunch status, and
   no team-selection or cut decision about a named student. Where the line is unclear, the content
   does not publish and Charlie decides.
8. **Former students are not automatically free.** An alum's name stays as it was published, and
   an alum who asks to be removed is removed exactly as a current student is.
9. **No student names in the site's machinery.** Image file names, file paths, commit messages,
   build logs and continuous-integration output carry no student name; photographs are referenced
   by an opaque consent reference instead.
10. **No student names in this repository outside published content.** Test fixtures, examples and
    documentation, including this policy, use invented names. A student name reaches the
    repository only inside `site/content/` or the allowlist below, which is to say only where it
    is already public on the site.

### The published-names allowlist

So that rules 1 and 2 can be checked by the build rather than by memory, the names the site is
permitted to print live in one reviewed list instead of being spread through the copy.

- The list holds every name the site may publish: coaches and other adults, the school, opponent
  schools, tournaments, and the team's students in their permitted form.
- Each student entry carries the name in its permitted form, the published form chosen
  (full name and class year, first name only, or no name), the graduation year where one is
  published, and the opaque media-consent reference where photographs are permitted. It carries no
  contact detail and no document.
- **Everything in the list is public by construction**: an entry exists only so that the same name
  may appear on a public page. Nothing is learned from the list that the site does not already say.
- A build fails when content contains a "First Last" name that is not in the list
  (`v1-e37-t03` acceptance criterion 3). **Editing or deleting an entry and republishing is how a
  name comes off the site**, which makes a removal request a content change rather than a code
  change.
- Charlie owns the list. A coach adds a student entry only after confirming the student is on the
  team and that no reduced-name request is on file; the district's consent records stay with the
  activities office.

`v1-e36-t04` builds the checks; this policy sets what they check.

## Photos and media consent

1. **A student photograph publishes only against a district media-consent form on file with the
   activities office**, covering that student and not withdrawn. No other basis counts: not a
   parent's verbal "sure", not a photo the student posted themselves, not a photo a tournament
   published, not a photo already on the district's own site.
2. **Unknown is no.** A student whose consent status cannot be confirmed with the activities
   office is treated as having no consent.
3. **A family that has opted out is never depicted**, including in a group shot they happen to
   stand in. **If one student in a photograph lacks consent, the photograph does not publish.** It
   is not cropped "closely enough", blurred, or published small.
4. **Consent is referenced, never copied into the repository.** Every image of an identifiable
   person carries an entry in the media-consent manifest (`v1-e36-t04` acceptance criterion 3):

   | Field | Example | Notes |
   |---|---|---|
   | Image path | `public/photos/novice-orientation-2026.jpg` | |
   | Consent reference | `MC-2026-014` | Opaque. Points at the form held by the activities office |
   | Who is depicted | `2 team members, both covered` | Counts and coverage. **No names** |
   | Date checked | `2026-09-18` | When a coach last confirmed the forms with the office |

   The mapping from a reference to a student is Charlie's, kept with the activities office's
   records and **not committed**. A build fails on any image of a person with no manifest entry.
5. **No photograph of an identifiable student who is not on this team**, and no photograph of
   another school's students, whoever took it.
6. **Metadata is stripped before publication.** Every image is exported without EXIF data: no
   location coordinates, no device identifier, no original file name, no capture timestamp.
7. **Captions and alt text follow [Students](#students)**, and name a student only in that
   student's published form. "A debater at the podium" is the default.
8. **Video and audio are photographs for the purpose of this section**, with the same consent
   requirement plus captions as required by [Accessibility](#accessibility). Nothing is embedded
   from a third-party video host; see
   [Analytics and third parties](#analytics-and-third-parties).
9. **Safe-by-default alternatives always exist** and are preferred when consent is uncertain: wide
   shots with no recognizable face, an empty competition room, trophies, a whiteboard, the team's
   own graphics.
10. **Screenshots count.** A ballot, a Tabroom bracket, a pairing sheet or a group-chat screenshot
    publishes every name on it and is subject to every rule above. In practice these do not
    publish.
11. **Consent is re-confirmed each season.** Before the first publication of each school year, a
    coach confirms with the activities office that each referenced form is still on file and not
    withdrawn, and updates the "date checked" field. A reference that cannot be re-confirmed means
    the image comes down.

## Results and awards

Results are what most families come to the site for, and they are also the content most likely to
name a child. Both facts are respected here.

1. **The published form, for a student whose name may be published:**
   - **Individual events** (Lincoln-Douglas debate, and any speech event the team enters) are
     published as full name, graduation year, event, tournament and placing, for example
     "Jordan Rivera, Class of 2028, Lincoln-Douglas debate, quarterfinalist".
   - **Partner events** (Policy debate, Public Forum debate) name **both** partners with both
     graduation years. A partnership is never published with one half named.
2. **Otherwise the result publishes in team-level form**, which is always available and is never
   treated as a lesser outcome to apologize for on the page:

   > "A Whitefish Bay Public Forum team reached quarterfinals at the Marquette tournament."

   This is the form used whenever a student in the result has asked for a reduced name, is not on
   the [allowlist](#the-published-names-allowlist), or where either partner's name may not be
   published.
3. **No record, ranking or rating of a student over time.** No win-loss record, no season points
   total, no speaker-point average, no bid count, no leaderboard, no "most improved" table, and no
   ranking of team members against one another. A single tournament placing is a result; an
   accumulated record is a profile, and this site does not profile minors.
4. **Nothing about losing, by name.** A result naming a student is published only where the
   student placed or advanced. The site does not publish elimination-round losses by name, records
   with losses in them, or a list of who did not break.
5. **No opponent students are named**, in any form, ever. Opponent *schools* may be named; the
   students debating for them may not.
6. **No ballots, no round-by-round detail, no reason for decision, and no critique of a student's
   performance.** Adults acting in a public judging capacity may be named as such.
7. **Results are facts Charlie supplies**, taken from the tournament's own published results. An
   implementation session never invents, estimates or reconstructs a result.
8. **A result comes down on request like anything else**, and a student who asks for a reduced
   name has their name taken out of every past result, which reverts to team-level form rather
   than being deleted outright.

## Branding

The school's name, mascot and marks belong to the district, not to this team.

1. **The site describes itself as the district required: "A team-run site for Whitefish Bay
   debate."** Every page's footer identifies the site as maintained by the debate team's coaches
   at Whitefish Bay High School, so no visitor mistakes it for an official district communication.
2. **School name, mascot and logo are used only as the district's conditions allow.** The
   activities director stated no conditions
   ([District approval and conditions](#district-approval-and-conditions)); if the district later
   states required wording, a required disclaimer, or a rule about the official district logo,
   that wording is used verbatim and is not edited for tone or length.
3. **No district or school mark is altered**: not recolored, stretched, rotated, cropped into a
   new mark, combined with other marks, or used as a background texture.
4. **The team's working brand reference is
   [`site/src/styles/tokens.css`](../../site/src/styles/tokens.css)**, the only place a color,
   type size or spacing step is defined. Its header records where the palette came from and the
   measured contrast ratio of every text-on-background pair the site uses, and
   `site/tests/tokens.test.ts` recomputes them from the file so they cannot drift. The palette was sampled by the operator from the team's
   own deck template, off the Blue Dukes "W BAY" wordmark, because **the district publishes no
   official hex codes**; that is [open question 1](#open-questions). If official colors are
   published, the tokens file is corrected to them within the limits in
   [Accessibility](#accessibility).
5. **Accessibility outranks brand fidelity**, and the site already reflects this
   (`v1-e36-t03`):

   | Color | Contrast on white | Restricted to |
   |---|---|---|
   | Muted grey `#74798E` | 4.31:1 | Large text (24px, or 18.66px bold) and non-text use such as borders and rules |
   | Warm accent `#B36B00` | 4.18:1 | The same |
   | Body grey `#55596B` | 6.94:1 | The fallback for small secondary copy, and unrestricted |

   Neither restricted color reaches the 4.5:1 that WCAG 2.1 AA asks of normal text, so rather than
   adjust the brand, both are confined to uses needing only 3:1. **A unit test fails the build if
   any stylesheet paints small text with either color.**
6. **Typeface.** The site downloads no font. It asks for Arial, as the team decks use, and falls
   back to metric-compatible faces already installed on each platform. That substitution is the
   only deliberate difference from the deck template.
7. **No sponsor logo, no vendor badge, no "powered by" mark** on any page, and no logo of any
   organization Charlie has not approved.
8. **Tournament, camp and organization names** (for example the National Speech and Debate
   Association) may be named in text. Their logos are not reproduced without permission.

## Accessibility

**WCAG 2.1 AA is the floor for every page on this site, not a goal.** A page that does not meet it
does not publish. Families using a screen reader, a keyboard, a phone or a school Chromebook are
who this rule exists for.

1. **Every page meets WCAG 2.1 level AA.** `axe-core` runs over every built page on the WCAG 2.1 A
   and AA rule sets and must report no violation (`v1-e36-t04` acceptance criterion 5). A
   violation is a build failure, not a backlog item.
2. **Contrast.** Normal text meets 4.5:1 against its background; large text and non-text elements
   such as borders and focus rings meet 3:1. Because `axe-core` cannot measure contrast without a
   layout engine, the ratios are asserted against the design tokens instead, as set out in
   [Branding](#branding) rule 5.
3. **Every image carries alt text** describing what the image conveys; decorative images carry
   empty alt text so a screen reader skips them. Alt text obeys [Students](#students).
4. **Video and audio carry captions**, and a transcript where the content is not otherwise on the
   page. A video without captions does not publish. Since nothing is embedded from a third-party
   host, captions are the team's to produce and are part of publishing the video at all.
5. **Keyboard first.** Every page is fully operable with a keyboard alone, starts with a skip
   link, shows a visible focus indicator, and uses `banner`, `main` and `contentinfo` landmarks.
   The mobile navigation opens with Enter or Space and closes with Escape, returning focus to its
   button.
6. **Mobile first.** Pages are laid out for a phone, need no horizontal scrolling, and give every
   interactive control a touch target of at least 44 by 44 pixels.
7. **Structure carries meaning.** One `<h1>` per page and headings in order; real lists and real
   tables with headers; meaning never carried by color alone; link text that makes sense out of
   context ("the parent FAQ", never "click here").
8. **Plain language for parents.** Body copy uses no em dashes and spells out every acronym the
   first time a page uses it, both enforced by the build
   ([`site/README.md`](../../site/README.md#house-style-enforced-by-the-build)). A parent with no
   debate background is the reader every page is written for.
9. **No document replaces a page.** Information parents need is on a web page. A PDF, if one is
   ever published, is tagged and accompanied by the same content in HTML.
10. **An accessibility statement is published**
    ([`site/content/pages/accessibility.md`](../../site/content/pages/accessibility.md)) giving the
    target, what has been done and how to report a problem. A reported accessibility problem is
    acknowledged within 3 business days and fixed or explained within 7 calendar days, the same
    clock as [Removal on request](#removal-on-request).

## Analytics and third parties

**The site loads nothing from anyone else.** A visitor here, who may be a minor, is not measured,
profiled, retargeted or sold, and nothing they do on this site reaches a company outside the
district's hosting path.

**Forbidden outright, on every page, with no exception for convenience:**

1. **Analytics tags and scripts of any kind**, from any vendor, including Google Analytics, Google
   Tag Manager, Plausible, Fathom, Matomo and Hotjar, or any self-hosted equivalent placed on the
   site.
2. **Advertising of any kind**: ad networks, ad slots, affiliate links, sponsored placements,
   retargeting pixels.
3. **Tracking pixels, beacons and conversion tags**, including a mailing provider's open- and
   click-tracking pixels.
4. **Embedded social widgets and feeds**: Facebook, Instagram, X, TikTok or YouTube embeds, like
   and follow buttons, share buttons that load vendor script, and comment systems. A plain text
   link out to a social account is allowed; the vendor's code is not.
5. **Remote fonts, stylesheets, scripts, icon sets and images from another origin**, including
   Google Fonts, a content delivery network's copy of a library, an avatar service or map tiles.
   Everything the browser loads is served from the team's own distribution.
6. **Third-party iframes**, including calendar embeds, form services, video players, donation
   widgets and chat bubbles. The events calendar (`v1-e37-t02`) renders data baked in at build
   time, never an embed.
7. **Cookies, `localStorage`, `sessionStorage` and browser fingerprinting**, for any purpose
   whatsoever. The site sets no cookie, so it needs no cookie banner, and it is honest when it
   says so.
8. **Any runtime backend.** The site is static files: no form handler, no API route, no
   middleware, no server action and no client-side fetch of visitor data.
   `site/tests/offline.test.ts` fails on a network call, and lint, test and build all run offline.

**Permitted, and only this:**

9. **No analytics at all is an acceptable answer**, and is the state the site launches in.
10. **CloudFront aggregate request data only.** If the team wants to know whether anyone reads the
    parent FAQ, the only permitted source is CloudFront's own aggregate reporting in the AWS
    console. Conditions, all binding:
    - **Nothing is added to a page.** No tag, no script, no cookie, no pixel. This measures the
      delivery path, not the visitor.
    - **Aggregates are read; logs are not mined.** No per-request log analysis, no address lookup,
      no geolocation of an individual, no session reconstruction, no profiling, and no joining of
      a request to a person.
    - **Nothing leaves AWS.** Reports are not exported into a third-party analytics tool, a
      spreadsheet service or a dashboard vendor.
    - **Retention is short.** Where standard logging is enabled at all, the log bucket expires
      objects **within 30 days** and is private with all block-public-access flags set
      (`v1-e36-t02`).
    - **Only counts are written down.** Anything recorded in `docs/data/` is an aggregate: no
      address, no user agent string, no referrer that identifies a person.

**Search indexing fails closed** (`v1-e36-t03`). Only a build marked as prod is indexable. Every
other build, including the dev preview, serves `noindex, nofollow` on every page and a
`robots.txt` that disallows all paths. The default with the setting unset is the safe one, so a
misconfigured build cannot put a preview of the team's students into a search engine.

**Outbound links.** Links to the district, to Tabroom, to the National Speech and Debate
Association and to the district's donation page are plain links a visitor chooses to follow, and
are visibly labeled when they leave the team site. **A service the site links to is not thereby
endorsed**, and this policy does not reach what that service does with a visitor who follows the
link.

**The one place a visitor hands data to another company** is the parent email-updates signup
(`v1-e37-t05`): the page says so in plain words, the provider's script is never loaded here, and
the platform never receives, proxies, logs or stores a subscriber's address.

## Donations

The district's donation process, the approved payment destination, receipts and the donor opt-in
wording are set by `docs/policies/donations.md` (`v1-e38-t01`) and are not restated here. This
section covers only what the **website** may do. **It is not legal or tax advice.**

1. **The site never handles money.** No payment form, no card or bank field, no payment iframe, no
   payment-provider script, no wallet button, no `cc-*` autocomplete attribute, and no code that
   resolves to a payment application.
2. **The donate page explains the need and links out** to the single destination approved in the
   donations policy. The link is visibly labeled as leaving the team site.
3. **The approved destination lives in a reviewed configuration file, not in editable copy**
   (`site/config/donations.json`, `v1-e38-t02`). A build fails if any donation link differs from
   it, or if the URL is not the one recorded in the donations policy. **A coach editing page copy
   cannot change where money goes.**
4. **No donor personal data on the platform, in any environment.** No name, email address, postal
   address, phone number or gift amount is collected, logged, proxied or stored by the site, this
   repository, continuous integration or AWS.
5. **Donor recognition is opt-in and minimal** (`v1-e38-t03`): a display name the donor chose, an
   optional season, and an opaque opt-in reference pointing at a written opt-in held outside the
   platform. "Anonymous" is always available, and a donor who has not opted in is not listed.
6. **No student name in a donor display name**, and no family described in a way that identifies a
   student.
7. **No gift amounts, no donor tiers by amount, no thermometer with named contributors, no
   ranking of donors.**
8. **The site makes no claim about tax treatment** and never implies the team issues a receipt;
   the donations policy supplies the district's own wording.
9. **No fundraising platform, crowdfunding widget or peer-to-peer campaign embed**, and no donation
   call to action aimed at students.
10. **A donor entry comes down on request**, the same as anything else.

## Removal on request

**Anything on this site comes down on request, without the requester having to justify it, and
without argument.** This is the rule a parent is most likely to need.

**Who may ask**

- Any student on the team, about themselves. A student does not need a parent's backing to have
  their own name or photograph taken down.
- Any parent or guardian, about their child.
- The district, the high school administration or the activities director, about anything.
- Any adult named on the site, about themselves.
- Any donor listed under E38, about their own entry.
- A coach, about anything published in error or outside this policy.

**How to ask.** By email to **charles.clark@wfbschools.org**, or through the contact channel
published on the site's Contact page (`v1-e36-t04`). The request names the page, the photograph or
the person; **no reason is required and none is weighed.** Charlie confirms the requester's
standing only where the request concerns someone other than the requester.

**Response times.** These match [caselist-data-use.md](caselist-data-use.md#removal), so there is
one clock across the project.

| Step | Within | Who |
|---|---|---|
| Acknowledge the request | **3 business days** | Charlie, or the coach who received it |
| Content removed from prod: content or allowlist entry edited, `site/` rebuilt, deployed, **and a CloudFront invalidation issued for the affected paths** (`/*` when in doubt) | **7 calendar days of the request** | Charlie, or a coach with deploy access, running `scripts/site_deploy.sh` (`v1-e36-t05`) |
| Content removed from the dev preview and from the content source, so the next build cannot restore it | The same run, before prod is redeployed | The same person |
| Written confirmation to the requester, naming what was removed and when | With the removal, inside the same 7 days | Charlie |

These are the maximum times the team commits to, not a target to fill. In practice a removal is a
content edit and a deploy, and it is done as soon as a coach can run it.

**The invalidation is not optional.** A CloudFront edge cache keeps serving a removed page or
image after the bucket has been updated. A removal is not complete until the invalidation has
finished and the person running it has loaded the affected URLs and seen the content gone.

**What removal does**

- Edits or deletes the content in `site/content/` (or the E37 content source), so the next
  scheduled rebuild cannot bring it back.
- Edits or deletes the person's entry in the
  [published-names allowlist](#the-published-names-allowlist), which makes any remaining mention
  of that name **fail the build** rather than republish.
- Deletes the image and its media-consent manifest entry, for a photograph request.
- Rewrites an affected result into its team-level form rather than deleting the team's result
  outright, unless the requester asks for the whole item to go.
- Is recorded in a removal log holding the date, what was removed by page and path, the
  requester's standing (student, parent, district, adult or donor), the consent reference where
  one applies, and the invalidation id. **The log holds no student name and is not committed to
  this repository.**

**What removal does not do**

- It does not reach the district's site, the school's social accounts, a tournament's results
  page, Tabroom, or a search engine's cache. The requester is told this plainly and, where it
  helps, told who to ask. Charlie may additionally ask a search engine to drop a cached copy; this
  policy does not promise a result that is not the team's to give.
- It does not reach a copy someone else already downloaded.
- It does not require the requester to explain themselves, now or later.

**Standing rule: when in doubt, take it down first and discuss afterwards.** Nothing on this site
is worth leaving up over an unresolved objection from a family.

## Pre-publication checklist

**Every change that reaches prod passes this checklist**, whether it is a new page (`v1-e36-t04`),
an announcement or calendar entry (E37), or a donation or donor-recognition change (E38). Reviews
in those tasks cite these items **by number**. A "no" on any item stops the publication until it
is fixed; there is no "publish and fix it after".

1. **Names.** Every person named in the change is in the
   [published-names allowlist](#the-published-names-allowlist), in the form the list permits.
   No surname appears for a student who has asked for a reduced name. No opponent student is
   named. ([Students](#students) 1, 2; [Results and awards](#results-and-awards) 5)
2. **Ages and grades.** No age, date of birth, grade level or birthday appears anywhere. A
   graduation year appears only as a class year beside a name that may be published.
   ([Students](#students) 1)
3. **Contact details.** No student email address, phone number, social handle, messaging username,
   home address, home town or personal website appears, in body copy, alt text, an image, a link
   or a file name. The only addresses in the change are coach or team addresses.
   ([Students](#students) 3)
4. **Photographs and consent.** Every image of an identifiable person has a media-consent manifest
   entry with a reference confirmed against the activities office, every person in the frame is
   covered, and EXIF metadata has been stripped. Alt text and captions follow the name rules.
   ([Photos and media consent](#photos-and-media-consent) 1, 3, 4, 6, 7)
5. **Sensitive content.** Nothing in the change touches discipline, grades, health, disability,
   family circumstance, immigration status or team-selection decisions about a named student.
   ([Students](#students) 7)
6. **Results.** Every named result uses the published form, names both partners in a partner
   event, and reports only a placing or advancement. No cumulative record, ranking, rating,
   leaderboard or loss by name. ([Results and awards](#results-and-awards) 1-4)
7. **Location and schedule.** No named student is paired with a specific room, ride, hotel,
   arrival time or solo travel plan. ([Students](#students) 5)
8. **Third-party content.** The change adds no script, iframe, embed, pixel, tracker, advertisement,
   social widget, remote font, remote stylesheet or remote image, and no cookie or browser
   storage. Every asset the browser loads is served from the team's own distribution.
   ([Analytics and third parties](#analytics-and-third-parties) 1-8)
9. **Outbound links.** Every link leaving the team site is labeled as doing so, and any donation
   link is exactly the approved URL from the reviewed configuration file.
   ([Donations](#donations) 2, 3)
10. **Money.** The change contains no form, input, payment field, payment iframe or payment script,
    and collects no donor data. ([Donations](#donations) 1, 4)
11. **Accessibility.** `axe-core` reports no WCAG 2.1 AA violation on the built pages, every image
    has appropriate alt text, any video has captions, headings are in order, and the change works
    with a keyboard alone on a phone-width screen. ([Accessibility](#accessibility) 1-7)
12. **Plain language.** No em dashes in body copy, every acronym spelled out on first use on the
    page, and a parent with no debate background could follow it.
    ([Accessibility](#accessibility) 8)
13. **Branding.** School name, mascot and marks are used unaltered and as the district's conditions
    allow; the footer identifies the site as team-run; no sponsor or vendor logo appears; colors
    come from the design tokens and no restricted color paints small text.
    ([Branding](#branding) 1-7)
14. **Indexing.** The change is being deployed to the environment intended, and a dev preview build
    still carries `noindex, nofollow` and the disallow-everything `robots.txt`.
    ([Analytics and third parties](#analytics-and-third-parties), search indexing)
15. **Removal path.** Everything the change publishes about a person can be taken down by editing
    content or the allowlist and redeploying, with no code change required.
    ([Removal on request](#removal-on-request))
16. **Sign-off.** For anything that names or depicts a student, **Charlie has seen the exact
    content that will publish** and approved it. A coach may publish an item naming nobody without
    a second pair of eyes; an item naming or depicting a student needs Charlie.

## Open questions

Status as recorded at the version 1.0 approval. **Accepted** means Charlie knowingly approved the
policy without the answer; **open** means the answer is still needed before the thing it gates.

| # | Question | Status | Who resolves it | What it blocks |
|---|---|---|---|---|
| 1 | The district's **official brand colors**. None are published, so the palette in `site/src/styles/tokens.css` was sampled from the team's own deck template and is the team's working reference | Open | Charlie, with the district communications office | Nothing today. If official colors appear, the tokens file is corrected within the contrast limits in [Accessibility](#accessibility) |
| 2 | **Who besides Charlie can take the site down** if he is unavailable, and how they do it (registrar access, AWS access, or a district contact who can reach him) | Open | Charlie | [Domains and continuity](#domains-and-continuity) 5. Should be answered before the first prod launch |
| 3 | Whether the activities office's **media-consent form covers website publication specifically**, and how often it is renewed or re-signed | Open | Charlie, with the activities office | Publishing the first student photograph. Until answered, photographs publish only where Charlie has confirmed the individual form with the office |
| 4 | Whether the district or the high school wants a **review of the site before it goes live to prod**, given that none was stated as a condition | Open | Charlie, with Randee Drew | The first prod launch (`v1-e36-t05`). Cheap to ask and awkward to skip |
| 5 | Whether the district would prefer the site under a **district-owned domain or district hosting** rather than domains registered to a coach personally | Open | Charlie, with the district | Nothing today. [Domains and continuity](#domains-and-continuity) records the risk in the meantime |
| 6 | A **brand asset set that survives the sizes the site needs**: the lockup and mark as SVG or transparent PNG, plus square icon artwork cropped to the W. Today's assets are opaque, recovered from a JPEG, and blur at icon sizes | Open | Charlie | Nothing. Recorded in the `v1-e36-t03` session report as follow-up work |

## Review and change control

- This policy is reviewed at the start of each season, and immediately whenever the district's
  conditions change, the media-consent process changes, domain ownership changes, a removal
  request cannot be honored as written, or an incident occurs.
- Changes are made by pull request against this file, with the version bumped in the header and
  the [Approval](#approval) section re-recorded. **A change that loosens a rule needs Charlie's
  approval before it takes effect; a change that tightens one takes effect on merge.**
- Downstream specs cite this file by path and cite the
  [Pre-publication checklist](#pre-publication-checklist) by item number, rather than copying its
  rules, so there is one source of truth.
- If a rule here turns out to be unworkable in a tournament weekend, the answer is to change the
  policy in a pull request, not to publish around it once.

## Approval

**Until this table records an approval, nothing this policy governs may be published.** That
covers the core pages (`v1-e36-t04`), the first prod deploy (`v1-e36-t05`), announcements and the
calendar (E37), and the donation page (E38).

| Field | Value |
|---|---|
| Policy version | 1.0 |
| Approved by | _Pending_ |
| Role | Product owner and head coach |
| Approval date | _Pending_ |
| Scope of approval | Sections [Scope](#scope) through [Review and change control](#review-and-change-control) of version 1.0, including the district approval recorded from Randee Drew on 2026-09-18 and the [Pre-publication checklist](#pre-publication-checklist) |
| Open questions accepted as known gaps | _Pending_ |
| Open questions left open | _Pending_ |

A later version is approved by editing this table in a pull request, with the version bumped in
the header and in [Review and change control](#review-and-change-control).

## References

- [docs/policies/caselist-data-use.md](caselist-data-use.md) — disclosed evidence and OpenEv camp
  files, and the removal clock this policy matches.
- `docs/policies/donations.md` (`v1-e38-t01`, not yet written) — the district's donation process
  and the approved payment destination.
- [ADR-0013: Two environments and dev to main promotion](../adr/0013-two-environments-and-dev-main-promotion.md)
  — why a dev preview exists and why it must never be indexed.
- [site/README.md](../../site/README.md) — the design tokens, the house style the build enforces,
  the brand assets, and what the site project must not do.
- Architecture proposal
  [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety).
- Specs that depend on this policy: `plan_specs/v1/e36-team-website/` (t04 core pages, t05 deploy),
  `plan_specs/v1/e37-calendar-and-announcements/` (t01 content editing, t03 announcements,
  t05 parent email signup), `plan_specs/v1/e38-donations/` (t02 donation page, t03 donor
  recognition).

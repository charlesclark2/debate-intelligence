# Session report: v1-e36-t01-publishing-policy

| | |
|---|---|
| Task | `v1-e36-t01-publishing-policy` — Website publishing and student-privacy policy |
| Spec | [`plan_specs/v1/e36-team-website/t01-publishing-policy.yaml`](../../plan_specs/v1/e36-team-website/t01-publishing-policy.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t01-publishing-policy` |
| Session status | COMPLETE |

## Summary

Wrote [`docs/policies/website-publishing.md`](../policies/website-publishing.md), the approved
policy that gates everything published on the public team website. It follows the shape of the
caselist data-use policy: version table, scope, numbered rules per subject, open questions and an
approval block. Charlie supplied the district's approval in this session (Randee Drew, Athletics
and Activities Director, 2026-09-18, **no conditions stated**), the media-consent arrangement
(forms signed by students and held by the activities office), the domains, the student naming
rule and the removal contact; none of it was inferred by the session. He read and approved
version 1.0 in this session, so the policy is live and t04, t05, E37 and E38 are unblocked.

**Second pass.** The PM returned the first pass CHANGES_REQUESTED with three items, and Charlie
resolved open question 3 in the same round. Both are addressed here, and they changed the policy's
shape rather than just its wording:

- **Consent is now the gate for a student's name, not just their photograph.** The PM's amended
  `ac3` ties the district's naming rule to a media-consent form on file, which also matches what
  Charlie said first in this session ("if a student has fully opted in"). The published form is
  `FIRST NAME LAST NAME (GRADUATION YEAR)`, and a student with no current form appears only inside
  a statement that names nobody.
- **Consent expires.** Randee Drew confirmed on 2026-09-20 that the district's form covers website
  publication **and renews annually**, so the policy gained a
  [Consent renewal and the start-of-season check](../policies/website-publishing.md#consent-renewal-and-the-start-of-season-check)
  section and a [Graduated students](../policies/website-publishing.md#graduated-students)
  section. That turned the PM's blanket "no student photographs" block into a consent-check gate,
  so `v1-e36-t04` may ship student photos once the season's forms are confirmed.
- **Student removals run on a 24-hour clock**, against 7 calendar days for everything else, with
  the page pulled outright if a deploy is not possible in time.

Two things beyond the spec's list were added because Charlie's answers raised them and nothing
else in the project covers them: a **Domains and continuity** section (both domains are registered
to Charlie personally, not the district, so the policy records who renews them and what happens if
he stops coaching), and a **published-names allowlist** that gives the E37 build check something
concrete to validate against and makes a removal request a content edit rather than a code change.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `policy-draft` — Policy skeleton and student rules | Done | Commit `e9f045c`. Version table, Scope, Students, Photos and media consent, Results and awards, Removal on request, with every district-specific fact left as a pending record rather than guessed. |
| `district-conditions` — Record the district approval and its conditions | Done | Commit `2c0db5a`. Charlie supplied the approver, role and date and stated that **no conditions** were attached; recorded as a fact and explicitly not read as permission. |
| `site-wide-rules` — Branding, accessibility, analytics and donation rules | Done | Commit `2c0db5a`. Records what `v1-e36-t03` already built (sampled palette, two restricted brand colours, fail-closed indexing) rather than re-deciding it; Donations cross-references `docs/policies/donations.md` instead of restating E38. |
| `prepublish-checklist` — Pre-publication checklist and docs index | Done | Commit `2c0db5a`. Sixteen numbered items, each citing the rules it enforces; policy linked from `docs/README.md` beside the caselist policy. |
| `charlie-approval` — Charlie approves the policy | Done | Charlie approved version 1.0 in this session; the approval table, the status line and the open-question dispositions were filled in from his answers. |
| *(second pass)* PM review items and open question 3 | Done | This commit. Consent-conditional naming per the amended `ac3`, the 24-hour student removal clock, consent renewal and the start-of-season check, graduated students, and the PM's spec amendment committed alongside. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **Goal ac1** — policy exists with a version table and the thirteen named sections | PASS | `for s in Scope "District approval and conditions" Students "Photos and media consent" "Results and awards" Branding Accessibility "Analytics and third parties" Donations "Removal on request" "Pre-publication checklist" "Open questions" Approval; do grep -c "^## $s\$" docs/policies/website-publishing.md; done` → `1` for all thirteen. Header table carries policy version, status, owner, written by, applies to, approved by and next review. |
| **Goal ac2** — District approval section records who, when and each condition as supplied; unknowns are open questions | PASS | Section records **Randee Drew, Athletics and Activities Director**, **2026-09-18**, and **"None stated"** for conditions, all as Charlie gave them in this session. Nothing was added or softened; the section says plainly that "none stated" is not read as permission. The section also records **Randee Drew's 2026-09-20 confirmation** that the district's media-consent form covers website publication and renews annually, recorded in the same form as the approval itself. The things the district has not answered are [open questions](../policies/website-publishing.md#open-questions) 1 and 5, not guesses. |
| **Goal ac3** (as amended by the PM) — district naming rule for students with media consent on file, consent check before publishing and each season, no contact details, photos only with consent confirmed for website use, removal procedure with a faster clock for student names and images | PASS | Checked clause by clause against the amended text. **Naming rule:** [Students](../policies/website-publishing.md#students) rule 1 gives `FIRST NAME LAST NAME (GRADUATION YEAR)` ("Jordan Rivera (2028)"), only for a student with a current-season form on file; rule 2 makes no form mean no name and unknown mean no; rule 4 makes it reducible or withdrawable at any time without a reason. **Consent check before publishing and each season:** rule 3 plus the [Consent renewal and the start-of-season check](../policies/website-publishing.md#consent-renewal-and-the-start-of-season-check) section, which names the activities office as where consent is tracked and Charlie as who confirms it, and checklist item 17, which gates the season's first deploy. **Contact details:** rule 6, forbidden with no exception at any consent level. **Photos with consent confirmed for website use:** [Photos and media consent](../policies/website-publishing.md#photos-and-media-consent) rule 1, citing Randee Drew's 2026-09-20 confirmation, with rule 11 requiring re-confirmation each season. **Removal with a faster student clock:** 3 business days to acknowledge, **24 hours** for a student's name or image (same day the goal) against 7 calendar days for other content, naming Charlie or a coach with deploy access running `scripts/site_deploy.sh`, requiring a CloudFront invalidation and a manual check of the affected URLs, and requiring the page to be pulled outright if a deploy is not possible inside 24 hours. |
| **Goal ac4** — Analytics section forbids trackers, ads, pixels and social widgets and permits only none or CloudFront aggregate reports; Accessibility sets WCAG 2.1 AA | PASS | `## Analytics and third parties` lists eight forbidden categories (analytics tags, advertising, pixels and beacons, social widgets and embeds, remote fonts/scripts/images, third-party iframes, cookies and browser storage, any runtime backend) and exactly two permitted states: no analytics at all, or CloudFront aggregate request data under five binding conditions. `grep -c "WCAG 2.1 AA"` → `3`; the Accessibility section opens "WCAG 2.1 AA is the floor for every page on this site, not a goal." |
| **Goal ac5** — checklist is a numbered list citable item by item, and status reads Approved with Charlie's name and date | PASS | `sed -n '/^## Pre-publication checklist$/,/^## Open questions$/p' … \| grep -cE '^[0-9]+\. \*\*'` → `18`. Sixteen per-change items plus two that run once a season (17, the start-of-season consent check; 18, the graduated-student photograph sweep). Each names the rules it enforces (e.g. item 4 → Photos and media consent 1, 3, 4, 6, 7, 11, 12), so a review can cite "checklist item 4". Status line reads `**Approved**, version 1.0, 2026-09-20`; the approval table records Charlie Clark, product owner and head coach, 2026-09-20. |
| `policy-draft` — Policy has a Students section (`contentMatch: "## Students"`) | PASS | `grep -c "^## Students$" docs/policies/website-publishing.md` → `1` |
| `policy-draft` — Policy has a removal-on-request section (`contentMatch: "## Removal on request"`) | PASS | `grep -c "^## Removal on request$" docs/policies/website-publishing.md` → `1` |
| `district-conditions` — Policy records the district approval (`contentMatch: "## District approval and conditions"`) | PASS | `grep -c "^## District approval and conditions$" docs/policies/website-publishing.md` → `1` |
| `district-conditions` — **custom:** Charlie confirms the section names the approver's role and date and lists every condition with nothing added or softened | PASS | Charlie supplied the content in this session and approved version 1.0 after reading it, with the approval table's scope line naming the district approval recorded from Randee Drew on 2026-09-18. The PM may want to re-confirm this at review, since the session is both the recorder and the reporter here. |
| `site-wide-rules` — Policy has the analytics and third-party rules (`contentMatch: "## Analytics and third parties"`) | PASS | `grep -c "^## Analytics and third parties$" docs/policies/website-publishing.md` → `1` |
| `site-wide-rules` — Policy sets WCAG 2.1 AA (`contentMatch: "WCAG 2.1 AA"`) | PASS | `grep -c "WCAG 2.1 AA" docs/policies/website-publishing.md` → `3` |
| `prepublish-checklist` — Policy has the pre-publication checklist (`contentMatch: "## Pre-publication checklist"`) | PASS | `grep -c "^## Pre-publication checklist$" docs/policies/website-publishing.md` → `1` |
| `prepublish-checklist` — Docs index links the policy (`contentMatch: "website-publishing.md"`) | PASS | `grep -n "website-publishing.md" docs/README.md` → line 15, in the table beside the caselist policy |
| `charlie-approval` — Policy status is Approved (`contentMatch: "**Approved**"`) | PASS | `grep -n "^| Status |" docs/policies/website-publishing.md` → `\| Status \| **Approved**, version 1.0, 2026-09-20. See [Approval](#approval). \|` |
| `charlie-approval` — **custom:** Charlie reads the policy end to end and confirms it may gate publishing | PASS (session) / **for PM re-confirmation in the PR** | Charlie was shown the `ac3` conflict, the superseded removal clock and the corrected contrast-row count, then answered "Approved — fill it in" and resolved two open questions in the same exchange. The spec asks him to confirm it **in the PR**, which the PM review section is where that happens. |
| Epic node `t01` — `uv run scripts/validate_specs.py --require-succeeded v1-e36-t01-publishing-policy` | PASS | → `v1-e36-t01-publishing-policy: Succeeded` |
| Repo-wide spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases` |
| Link check (not a spec criterion) | PASS | Every relative link and in-page anchor in the policy resolves; script output `missing anchors: none` / `missing files: none`. |

## Files changed

- **`docs/policies/website-publishing.md`** (new, ~480 lines) — the policy itself.
- **`docs/README.md`** — one row in the documentation index, beside the caselist data-use policy.
- **`plan_specs/v1/e36-team-website/t01-publishing-policy.yaml`** — task Goal `status.phase`
  `InProgress` → `Succeeded`, via `scripts/task_helper.py`. No other spec field was touched; in
  particular `ac3` and the `forbidden` list are as the PM wrote them.
- **`docs/session-reports/v1-e36-t01-publishing-policy.md`** — this report.

No code, test or infrastructure file was changed. The task's `constraints.packages`
(`docs/policies`, `docs/README.md`) were respected.

## Deviations from the spec

**None outstanding.** The one deviation from the first pass has been resolved by the PM amending
the spec, and the amendment is committed here.

**Resolved: student naming.** The first pass reported `ac3` as FAIL-as-written, because the policy
stated the district's naming rule where the spec required "first names or no names". The PM
rewrote `ac3` in this worktree to ask for the district's rule, and this session committed that
amendment alongside the policy. `ac3` now reads PASS against the amended text.

One thing the PM's amendment settled that Charlie's two answers had left ambiguous, and which the
PM should confirm is what he intended: **the amended `ac3` ties the naming rule to "students with
media consent on file"**, so a name is now consent-conditional rather than a default for any team
member. Charlie's first answer in this session supported that ("if a student has fully opted in,
their full name can be used"); his later message read more like a default ("default is first name,
last name, and graduation year; no student photos without the district's media consent on file").
**The policy follows the amended spec, which is the stricter of the two readings.** If Charlie
meant that names need no form and only photographs do, that is a one-line change to
[Students](../policies/website-publishing.md#students) rules 1 and 2, plus checklist item 1.

**Two sections the spec did not list**, both added because Charlie's answers raised something
nothing else in the project covers, and neither loosens a rule:

- **Domains and continuity** — `wfbdebate.org` and `wfbdebate.com` are registered to Charlie
  personally, not the district. The section records who renews them, that both domains, the AWS
  account and the repository are offered to the district or an incoming head coach if he stops
  coaching, that an unmaintained site is taken down rather than left running, and that a takedown
  deletes objects and issues an invalidation rather than only repointing DNS.
- **The published-names allowlist** (a subsection of Students) — one reviewed list of the names
  the site may print, so `v1-e37-t03`'s "name not on the allowlist fails the build" criterion has
  something concrete to check, and so a removal is a content edit rather than a code change.

**Two more sections added in the second pass**, required by the amended `ac3` and by Charlie's
resolution of open question 3:

- **Consent renewal and the start-of-season check** — consent expires at the end of each season;
  nothing publishes about a student whose current-season form is not on file, including content
  that was fine last season; Charlie verifies every named or pictured student against the current
  season's forms before the first publish of a new season; anyone not renewed comes off until
  their form arrives, quietly and with no implication about the student.
- **Graduated students** — results and rosters stay as the record of their season, photographs
  come down at the end of the following season, and any removal request is honored at any time
  regardless. This is Charlie's recommendation, adopted as written.

## Decisions and assumptions

1. **"No conditions stated" is recorded as a fact, not read as permission.** The policy says so
   explicitly, and says that its student, results, third-party and removal rules are stricter than
   anything the district asked for and stay that way unless the policy is revised. This mirrors
   the caselist policy's "more restrictive than the source terms require" posture.
2. **Unknown consent is treated as no consent**, for names, photographs and anything else, and
   **a form from a previous season counts as unknown.** The site never publishes on the
   assumption that consent probably exists or that last season's form is still good.
3. **Contact details have no consent exception.** Consent to publish a name is not consent to
   publish a way to reach a child, so no tier and no form makes a student's email, phone, handle
   or address publishable.
4. **Results carry rules the spec did not ask for**: no cumulative record, ranking, rating,
   leaderboard or speaker-point average, and no losses by name. A single placing is a result; an
   accumulated record is a profile of a minor. If the PM or Charlie wants season records on the
   site, that is a policy revision, not an exception.
4a. **A lapsed consent is removed quietly.** The policy says the takedown is not announced, not
   explained to anyone who did not ask, and carries no implication that the student did anything.
   A start-of-season sweep that visibly singles out students whose paperwork is late would be its
   own harm.
4b. **The name form follows the amended spec literally**: `FIRST NAME LAST NAME (GRADUATION YEAR)`,
   rendered "Jordan Rivera (2028)". The first pass used "Jordan Rivera, Class of 2028", which
   reads better for parents; the spec's form won because it is now the spec's form. Worth a word
   from the PM if the friendlier rendering was intended.
5. **The contrast-measurement count was corrected.** Charlie's message said "all fifteen
   measurements are in the site's tokens file header"; the header actually holds **thirteen**
   rows (nine passing plus four restricted). The policy cites "every measured text-on-background
   pair" rather than a number that would drift, and the specific figures it does quote
   (`#74798E` 4.31:1, `#B36B00` 4.18:1, `#55596B` 6.94:1) were verified against
   `site/src/styles/tokens.css`.
6. **Donations cross-references rather than restates.** Per Charlie's boundary note, the
   Donations section covers only what the website may do and points at `docs/policies/donations.md`
   (`v1-e38-t01`, not yet written) for the district's process, the approved destination, receipts
   and opt-in wording. The same is done for the caselist policy and for the V2 application.
7. **Example names in the policy are invented** ("Jordan Rivera", `MC-2026-014`), and the policy
   states that rule about itself. No real student name, photograph or contact detail appears
   anywhere in the file.
8. **The removal contact published is `charles.clark@wfbschools.org`**, the school address Charlie
   supplied, rather than the personal address the caselist policy uses. A school address is the
   right one to put in front of parents on a public school-team site.
9. **Session-level checks only.** Everything run for this task is a `grep`, a link check or
   `validate_specs.py`; nothing took more than a couple of seconds, so no command needed the
   operator.
10. **The 24-hour student clock also covers removals nobody asked for.** A consent that lapses at
    the start-of-season check runs on the same timetable as a parent's request, because the site
    has no more right to the content in one case than the other.
11. **Graduated students keep their results, lose their photographs.** Charlie's recommendation,
    adopted as written: a team record that deletes its own history serves nobody, while a
    photograph is a likeness with no expiry date and the consent behind it has lapsed. Any removal
    request is honored at any time regardless.

## Operator follow-ups

None required to merge this task. Four things the policy now commits Charlie to, listed here so
they are not lost:

1. **Run the start-of-season consent check before the first publish of each season**
   ([checklist item 17](../policies/website-publishing.md#pre-publication-checklist)): verify every
   student named or pictured on the live site against the current season's forms with the
   activities office, update each date checked, and take down anyone not yet renewed. The
   district's form renews annually, so this is now a standing obligation, not a one-off.
2. **Before `v1-e36-t04` publishes any student name or photograph**, confirm the current season's
   forms for every student it names or pictures. This is the gate that replaced the first pass's
   blanket photo block.
3. **Turn auto-renewal on for `wfbdebate.org` and `wfbdebate.com`**, and check that the registrar
   account's contact address is one Charlie will still read after he stops coaching
   ([Domains and continuity](../policies/website-publishing.md#domains-and-continuity) 1).
4. **When `v1-e36-t02` provisions the distributions**, set the CloudFront standard-log bucket (if
   logging is enabled at all) to expire objects within 30 days, private with all four
   block-public-access flags, as
   [Analytics and third parties](../policies/website-publishing.md#analytics-and-third-parties)
   item 10 requires.

## Follow-up work

1. **`v1-e36-t04` must build three things this policy assumes**: the media-consent manifest
   (already in its `ac3`), the **published-names allowlist**, and a **date-checked field** on both
   that the start-of-season check updates. Its spec mentions only the first, although
   `v1-e37-t03`'s `ac3` depends on an allowlist existing. Worth a line in `t04`'s spec so it is
   not discovered during E37.
2. **The start-of-season check wants tooling, not just a checklist item.** Verifying every named
   and pictured student by hand each August is exactly the kind of task that gets skipped in a
   busy season. A build-time warning when any allowlist or manifest entry's date checked predates
   the current season would make a lapse visible without anyone remembering to look. Probably
   `v1-e36-t04` or a small follow-up task; the PM's call.
3. **Confirm the consent-conditional naming reading with Charlie.** The amended `ac3` makes a
   student's name require a form on file; Charlie's two answers in this session pointed slightly
   different ways. See [Deviations](#deviations-from-the-spec).
4. **Give a second person the ability to take the site down** (registrar and AWS access), accepted
   as a known gap at approval
   ([open question 2](../policies/website-publishing.md#open-questions)). Today the only
   redundancy is that the activities office can reach Charlie. The 24-hour student removal clock
   makes this sharper than it was: one unavailable person is now the difference between meeting
   and missing the commitment.
5. **`docs/policies/donations.md` does not exist yet.** This policy links to it by path, so the
   link is dead until `v1-e38-t01` ships. Deliberate, and noted in the References section.
6. **A `docs/policies/README.md` index** would be worth having now that the directory holds two
   policies with a third coming. Not this task's scope.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20 (round 2)

**Notes (round 2):**

- All three round-1 items are addressed, plus the amended ac3 and Charlie's answer on consent.
- The consent-conditional reading of the naming rule is correct and stays: the district's rule is
  "students who have opted into media are listed as FIRST NAME LAST NAME (GRADUATION YEAR)", so a
  student with no current form is not named at all, not named in a reduced form. Keep the literal
  render, "Jordan Rivera (2028)"; "Class of 2028" may appear in prose but not in the roster entry.
- The consent-renewal section, the graduated-students rule and the two-speed removal clock (24 hours
  for a student's name or image, 7 calendar days otherwise, page deleted and invalidated if a deploy
  cannot happen in time) are all accepted as written.
- Follow-up 2 (a build-time warning when a consent check predates the current season) is worth doing
  and the PM is placing it in v1-e36-t04, where the roster content and its validation live. It is not
  a condition of this task.

**Round 1 notes, kept for the record:**

The policy itself is strong: the district approval is recorded as given, the "none stated" framing is
right, the checklist gives later tasks something to cite, and the Domains and continuity section is a
good catch that no other document covered.

1. ac3 amended by the PM in this worktree rather than failed: the spec predated the district's rule.
2. Faster clock for students: 24 hours for a name or image, 7 calendar days for other content.
3. No student photographs until open question 3 was answered (since resolved: photos are allowed once
   the season's consent forms are confirmed).

Fix the count reference as you described (cite "every measured pair", not a number). Then commit the
policy, the spec change and this report, keep the phase Succeeded, and send it back for a second pass.

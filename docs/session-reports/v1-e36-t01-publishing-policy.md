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

**The one thing for the PM to look at first is a real conflict between the district's rule and the
spec.** Charlie's district rule is that a student's **full name and graduation year** may be
published, which the spec's `ac3` and `forbidden` list both rule out ("first names only or no
names, never surnames, grades or ages paired with a name"). Charlie was shown the conflict
explicitly and chose to have the policy state the district's rule and have the PM amend the spec.
The session did not edit `ac3`. See [Deviations](#deviations-from-the-spec).

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
| `charlie-approval` — Charlie approves the policy | Done | The approval commit, which is also the commit carrying this report. Charlie approved version 1.0 in this session; the approval table, the status line and the open-question dispositions were filled in from his answers. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **Goal ac1** — policy exists with a version table and the thirteen named sections | PASS | `for s in Scope "District approval and conditions" Students "Photos and media consent" "Results and awards" Branding Accessibility "Analytics and third parties" Donations "Removal on request" "Pre-publication checklist" "Open questions" Approval; do grep -c "^## $s\$" docs/policies/website-publishing.md; done` → `1` for all thirteen. Header table carries policy version, status, owner, written by, applies to, approved by and next review. |
| **Goal ac2** — District approval section records who, when and each condition as supplied; unknowns are open questions | PASS | Section records **Randee Drew, Athletics and Activities Director**, **2026-09-18**, and **"None stated"** for conditions, all as Charlie gave them in this session. Nothing was added or softened; the section says plainly that "none stated" is not read as permission. The four things the district has not answered are [open questions](../policies/website-publishing.md#open-questions) 1, 3, 4 and 5, not guesses. |
| **Goal ac3** — student rules state first names or no names, no contact details, photos only with district media consent, removal procedure naming who acts and the target takedown time including a CloudFront invalidation | **FAIL as written / PASS as amended** | The contact-details, photo-consent and removal parts all PASS: contact details are forbidden at every tier with no consent exception; photographs require a form on file with the activities office and unknown status is treated as no consent; removal names Charlie or a coach with deploy access, commits to 3 business days to acknowledge and 7 calendar days to remove from prod, and requires a CloudFront invalidation plus a manual check of the affected URLs before a takedown counts as done. **The naming part does not match the spec**: the policy states the district's rule (full name and graduation year by default, reducible to first name or no name on request) instead of "first names or no names". Charlie's decision; needs a PM amendment to `ac3` and to the `forbidden` list. See [Deviations](#deviations-from-the-spec). |
| **Goal ac4** — Analytics section forbids trackers, ads, pixels and social widgets and permits only none or CloudFront aggregate reports; Accessibility sets WCAG 2.1 AA | PASS | `## Analytics and third parties` lists eight forbidden categories (analytics tags, advertising, pixels and beacons, social widgets and embeds, remote fonts/scripts/images, third-party iframes, cookies and browser storage, any runtime backend) and exactly two permitted states: no analytics at all, or CloudFront aggregate request data under five binding conditions. `grep -c "WCAG 2.1 AA"` → `3`; the Accessibility section opens "WCAG 2.1 AA is the floor for every page on this site, not a goal." |
| **Goal ac5** — checklist is a numbered list citable item by item, and status reads Approved with Charlie's name and date | PASS | `sed -n '/^## Pre-publication checklist$/,/^## Open questions$/p' … \| grep -cE '^[0-9]+\. \*\*'` → `16`. Each item names the rules it enforces (e.g. item 4 → Photos and media consent 1, 3, 4, 6, 7), so a review can cite "checklist item 4". Status line reads `**Approved**, version 1.0, 2026-09-20`; the approval table records Charlie Clark, product owner and head coach, 2026-09-20. |
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

**1. Student naming: the policy states the district's rule, not the spec's.** This is the one
deviation and it needs a PM spec change.

| | |
|---|---|
| What the spec says | `ac3`: "The student rules state **first names or no names**…". `spec.description`: "first names only or no names, **never surnames, grades or ages paired with a name**". `constraints.forbidden` carries the same rule |
| What the district's rule is, per Charlie | The default published form is **first name, last name and graduation year**. A student or family may ask for less (first name only, or no name) at any time, without a reason, and it is honoured |
| What the policy says | The district's rule, with the opt-down in [Students](../policies/website-publishing.md#students) rule 2, plus rules the spec did not ask for that narrow it: no age, date of birth, grade level or birthday ever; no cumulative record, ranking or rating of a student; no losses by name; no opponent students named; team-level form used whenever any named student has asked for less |
| How it was decided | The session stopped and put the conflict to Charlie verbatim, with the spec text quoted, offering (a) keep the spec's stricter rule and record that the district would permit more, (b) write the district's rule and have the PM amend the spec, or (c) full names for results only. **He chose (b).** |
| What the PM needs to do | Amend `ac3`, `spec.description` and `constraints.forbidden` in `t01-publishing-policy.yaml` to the district's rule before merging, or send it back with option (a). The session deliberately did **not** edit the spec, per CLAUDE.md |

**2. Two sections the spec did not list.** Both were added because Charlie's answers raised
something nothing else in the project covers, and neither loosens a rule:

- **Domains and continuity** — `wfbdebate.org` and `wfbdebate.com` are registered to Charlie
  personally, not the district. The section records who renews them, that both domains, the AWS
  account and the repository are offered to the district or an incoming head coach if he stops
  coaching, that an unmaintained site is taken down rather than left running, and that a takedown
  deletes objects and issues an invalidation rather than only repointing DNS.
- **The published-names allowlist** (a subsection of Students) — one reviewed list of the names
  the site may print, so `v1-e37-t03`'s "name not on the allowlist fails the build" criterion has
  something concrete to check, and so a removal is a content edit rather than a code change.

**3. The removal clock changed during the session.** Asked early, Charlie chose same-day
acknowledgement and a 24-hour prod takedown; his later message asked for the caselist policy's
clock instead (acknowledge in 3 business days, act within 7 calendar days). **The later
instruction was followed.** The policy adds one sentence that these are the maximum times
committed to, not a target to fill. Worth the PM's attention: seven days is a long time for a
photograph of a minor to stay up after a parent has asked for it to come down, and the tighter
number was Charlie's own first instinct. Changing it later is a one-line policy revision.

## Decisions and assumptions

1. **"No conditions stated" is recorded as a fact, not read as permission.** The policy says so
   explicitly, and says that its student, results, third-party and removal rules are stricter than
   anything the district asked for and stay that way unless the policy is revised. This mirrors
   the caselist policy's "more restrictive than the source terms require" posture.
2. **Unknown consent is treated as no consent**, for photographs and for anything else. The site
   never publishes on the assumption that consent probably exists.
3. **Contact details have no consent exception.** Consent to publish a name is not consent to
   publish a way to reach a child, so no tier and no form makes a student's email, phone, handle
   or address publishable.
4. **Results carry rules the spec did not ask for**: no cumulative record, ranking, rating,
   leaderboard or speaker-point average, and no losses by name. A single placing is a result; an
   accumulated record is a profile of a minor. If the PM or Charlie wants season records on the
   site, that is a policy revision, not an exception.
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

## Operator follow-ups

None required to merge this task. Three things the policy now commits Charlie to, listed here so
they are not lost:

1. **Confirm the activities office's media-consent form covers website publication specifically,
   and how often it is renewed** ([open question 3](../policies/website-publishing.md#open-questions)).
   This gates the first student photograph on the site, so it matters before `v1-e36-t04` ships
   any photo.
2. **Turn auto-renewal on for `wfbdebate.org` and `wfbdebate.com`**, and check that the registrar
   account's contact address is one Charlie will still read after he stops coaching
   ([Domains and continuity](../policies/website-publishing.md#domains-and-continuity) 1).
3. **When `v1-e36-t02` provisions the distributions**, set the CloudFront standard-log bucket (if
   logging is enabled at all) to expire objects within 30 days, private with all four
   block-public-access flags, as
   [Analytics and third parties](../policies/website-publishing.md#analytics-and-third-parties)
   item 10 requires.

## Follow-up work

1. **Amend `ac3`, `spec.description` and `constraints.forbidden` in
   `t01-publishing-policy.yaml`** to the district's naming rule. PM, in a specs pull request. See
   [Deviations](#deviations-from-the-spec) 1. Until this lands, `ac3` reads as failed against the
   spec as written.
2. **`v1-e36-t04` must build two things this policy assumes**: the media-consent manifest (already
   in its `ac3`) and the **published-names allowlist**, which its spec does not yet mention
   although `v1-e37-t03`'s `ac3` depends on one existing. Worth a line in `t04`'s spec so it is
   not discovered during E37.
3. **Reconsider the 7-day prod takedown** for content depicting or naming a student. See
   [Deviations](#deviations-from-the-spec) 3.
4. **Give a second person the ability to take the site down** (registrar and AWS access), accepted
   as a known gap at approval
   ([open question 2](../policies/website-publishing.md#open-questions)). Today the only
   redundancy is that the activities office can reach Charlie.
5. **`docs/policies/donations.md` does not exist yet.** This policy links to it by path, so the
   link is dead until `v1-e38-t01` ships. Deliberate, and noted in the References section.
6. **A `docs/policies/README.md` index** would be worth having now that the directory holds two
   policies with a third coming. Not this task's scope.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

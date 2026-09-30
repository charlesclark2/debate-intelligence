# Session report: v1-e37-t01-content-editing-decision

| | |
|---|---|
| Task | `v1-e37-t01-content-editing-decision` — How coaches edit content (ADR-0015) |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t01-content-editing-decision.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t01-content-editing-decision` |
| Session status | PARTIAL — waiting on three human steps (second-coach dry-run, team account with a second owner, Charlie's approval) |

## Summary

ADR-0015 is drafted as **Proposed**. It decides that **events come from a public team Google
Calendar, announcements from a Google Sheet whose protected Published tab is the only thing
published, and page text stays in git**. One new **team Google account** with two owners owns
both, and it is named as the target owner of v1-e37-t05's parent email list. Four options were
scored against the five fixed criteria plus Charlie's two (works on a phone, coach onboarding and
offboarding), with Charlie's weights (usability ×3, ownership ×2, added criteria ×1; cost, PII and
static fit as pass/fail gates). Vendor facts were measured from vendor pages and read-only requests
on 2026-09-29. The results: Calendar 33, Sheets 30, Sanity 24, git-backed CMS 15, out of 35.
The coach guide and the accounts runbook are written. **The task stays InProgress.** No second
coach was available for the dry-run (ac3), the team account and its second owner don't exist yet
(ac4), and the ADR can't be Accepted (ac1) until both have happened and Charlie approves.
**Look first at:** an out-of-scope finding. The site's published contact address is on
`wfbschools.org`, a domain that is **not registered**; see Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Criteria, weights and options matrix (`criteria-and-options`) | Done, one confirmation outstanding | Charlie added two criteria and chose weights on 2026-09-29. Charlie has not yet explicitly confirmed that the four options are all the options to consider |
| Prototype top options and coach dry-run (`prototype-and-dry-run`) | **Not run** | Prototype designed: test calendar and sheet (runbook, Test resources), plus a throwaway checker kept outside the repo. The dry-run is scripted in the ADR with a results table to fill. No second coach available |
| Accept ADR-0015 and index it (`accept-adr`) | Partial | Indexed as Proposed and the reservation row removed. Acceptance waits on the dry-run and Charlie's approval |
| Operator creates team-owned accounts (`operator-accounts`) | Runbook written, accounts **not created** | `docs/runbooks/website-content-accounts.md`; the owners table is waiting for the operator |
| Coach website editing guide (`coach-website-editing`) | Written, **not coach-reviewed** | `docs/guides/coach-website-editing.md`, with screenshot-to-add markers |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: ADR-0015 is Accepted, scores the four options on the five criteria plus Charlie's, and names one events source and one announcements/page source | **NOT RUN** (content done; not Accepted) | Scoring, criteria, weights and the named sources are in the ADR. `grep -c 'Status: Accepted' docs/adr/0015-website-content-editing.md` → `0`. It can't be Accepted until the dry-run is done and Charlie approves |
| ac2: the ADR states that keys and tokens live only in env or the CI secret store, build-time fetch with a last-good fallback, and how content-only edits relate to the ADR-0013 dev→main flow | PASS | ADR Decision points 5, 6 and 7. Point 6 adds that a fallback may never undo a takedown |
| ac3: a coach other than Charlie completes the dry-run, and the time taken and friction are recorded | **NOT RUN** | No second coach available (Charlie, 2026-09-29). The ADR's Dry-run section holds the script and an empty results table |
| ac4: accounts exist under a team-owned identity with two owners and a documented recovery path, in the runbook with no secrets | **NOT RUN** (runbook PASS) | Runbook written with owners, recovery, coach access and secrets tables. The account isn't created and the second owner isn't named (operator steps; forbidden to an agent) |
| ac5: the guide explains in plain language adding, editing and removing events and announcements, the student rules, how long until changes appear, and who to contact | PASS | `docs/guides/coach-website-editing.md` sections: Events, Announcements, Never post these about students, How long until changes appear (today: when Charlie runs `scripts/site_deploy.sh`; v1-e37-t04 named as what changes it), When something goes wrong |
| Node `criteria-and-options`: ADR draft contains "Ownership continuity" | PASS | `grep -c -F 'Ownership continuity' docs/adr/0015-website-content-editing.md` → `3` |
| Node `criteria-and-options`: Charlie's custom criteria and weights recorded | PASS, one part open | Recorded in the ADR's Criteria and weights section. Charlie's confirmation that the options list is complete is still to come |
| Node `prototype-and-dry-run`: coach dry-run completed without code | NOT RUN | As ac3 |
| Node `prototype-and-dry-run`: ADR contains "Dry-run" | PASS | `grep -c -F 'Dry-run' …` → `2`. The section exists but holds no results yet |
| Node `accept-adr`: ADR contains "Status: Accepted" | NOT RUN | Proposed, as above |
| Node `accept-adr`: ADR index lists 0015-website-content-editing.md | PASS | `grep -c -F '0015-website-content-editing.md' docs/adr/README.md` → `1` |
| Node `accept-adr`: Charlie approves ADR-0015 | NOT RUN | Waiting on Charlie |
| Node `operator-accounts`: runbook contains "Second owner" | PASS | `grep -c -F 'Second owner' docs/runbooks/website-content-accounts.md` → `2` |
| Node `operator-accounts`: accounts created and team-owned | NOT RUN | Operator step |
| Node `coach-guide`: guide cites website-publishing.md | PASS | `grep -c -F 'website-publishing.md' docs/guides/coach-website-editing.md` → `1` |
| Node `coach-guide`: guide reviewed by a coach | NOT RUN | Done in the dry-run |
| Links and specs | PASS | `uv run scripts/check_links.py` → `OK: 1107 relative links and anchors in 145 Markdown files`. `uv run scripts/validate_specs.py` → `OK: 289 files, 38 epics, 231 tasks, 20 releases` |

## Files changed

- `docs/adr/0015-website-content-editing.md`: new. The decision record, as Proposed.
- `docs/adr/README.md`: index row for 0015. The reservation row and the "0015 is reserved" note are
  removed.
- `docs/guides/coach-website-editing.md`: new. The coach guide.
- `docs/runbooks/website-content-accounts.md`: new. The team identity, owners, coach access,
  recovery, secrets, the t05 reconciliation, and the dry-run test resources.
- `docs/README.md`: index lines for the new guide and runbook (see Deviations).
- `docs/session-reports/v1-e37-t01-content-editing-decision.md`: this report.

No site code, fetcher or test was written, per the spec's boundaries. The prototype checker lives
outside the repository.

## Deviations from the spec

- **`docs/README.md` is outside `constraints.packages`** (`docs/adr`, `docs/guides`,
  `docs/runbooks`). Working agreement 3 requires every new document to get a line in that index, so
  two lines were added. Nothing else in the file changed.
- **The ADR decides "page text stays in git".** The epic says page text is edited through a CMS, and
  the spec asks for "one announcements/page source". The ADR names the sheet for announcements and
  keeps page text in `site/content/` under Charlie. Page text is structured YAML and Markdown guarded
  by the build, changes a few times a season, and moving it out of git would lose the review and
  promotion it gets today. Charlie should confirm this when approving the ADR. If the PM wants coaches to edit page
  text, that is a spec change.
- **Photos are excluded from sheet announcements.** v1-e37-t03 allows an optional image with a
  media-consent flag. The ADR routes every photograph through Charlie and the repository's
  media-consent manifest instead, because a sheet can't carry the manifest entry the publishing
  policy requires. t03's image criterion would then apply only to repository content. The PM
  should decide whether t03's spec needs amending.

## Decisions and assumptions

- **Criteria and weights** (Charlie, 2026-09-29): added "works on a phone" and "coach onboarding and
  offboarding". Usability ×3, ownership ×2, added ×1. $0, no PII and static fit are pass/fail gates,
  since the spec forbids failing them anyway.
- **Identity** (Charlie, 2026-09-29): a new team Google account, not a district role mailbox. The
  research added support for this: Workspace admins can restrict external calendar sharing to
  free/busy and can turn off publish-to-web, and a Workspace calendar can only be transferred within
  the organisation.
- **Two owners of a single Google account** means two people who can each sign in and recover it
  alone: each has their own passkey, the recovery email is the second owner's and the recovery phone
  is Charlie's. Day-to-day, both owners also have "Make changes and manage sharing" (calendar) and
  Editor (sheet) on their own accounts.
- **No secret is needed to read content.** The public ICS address and the published CSV answered
  keyless requests. Both the Calendar API and the Sheets API refused keyless requests, so the build
  uses the addresses rather than the APIs. The addresses are still kept out of git so they can be
  changed.
- **A fallback may not undo a takedown**: added to the build-time rule, because a last-good
  snapshot could otherwise republish something a family asked to have removed.
- **Hosted CMS representative: Sanity.** Along with Contentful, it is the only free tier that is
  perpetual and allows two owners at $0. Chosen over Contentful for Google sign-in and no hard
  monthly pause on delivery.
- **Prototype outside the repository**, as the PM directed: test resources in the team account, plus
  a standard-library checker (`prototype_check.py`) in the session scratchpad that reads the public
  ICS and published CSV and reports what the conventions can't read. It was tested offline against
  synthetic Google-style fixtures. Nothing from it is committed.
- **Contact address in the guide** is `charles.clark@wfbschools.com`, the district domain that
  receives mail (Google MX) and the address t05 registered Buttondown to, not the site's
  `wfbschools.org` address (see Follow-up work).
- **Still unconfirmed from vendor pages**: whether a public calendar's feed carries guests'
  addresses (the runbook's Step 4 tests it on the test calendar; the guide forbids guests either
  way), and Google's and Apple's refresh intervals for subscribed calendars.

## Operator follow-ups

In order. None needs a terminal except the last.

1. **Confirm the options list** (the four in the ADR are complete) and **confirm "page text stays in
   git"**. Tell the session or the PM.
2. **Create the team Google account and name a second owner.** Runbook Step 1 (~15 min). The second
   owner doesn't have to be the dry-run coach, but ac4 can't pass without one.
3. **Build the prototype**: the runbook's Steps 2 and 3, with `(test)` in the names (~30 min). Run
   the Step 4 checks, including the guest-address check.
4. **Run the dry-run** with a coach other than you, using only `docs/guides/coach-website-editing.md`
   and the script in the ADR's Dry-run section. Record times and friction in words; ~20 min of their
   time.
5. **Check the entries are machine-readable** (read-only, a few seconds). Copy the checker out of the
   session scratchpad first; it is temporary and not in the repo:

   **Operator command** (expected runtime <10 s)
   Where: your Mac, any directory outside the repository
   ```bash
   python3 prototype_check.py --ics "<test calendar public iCal address>" --csv "<test sheet Published tab CSV address>"
   ```
   Success looks like: the tournament and announcement listed with their fields, and `== 0 problem(s)`.
   Paste the output back into the session.
6. Resume this task (`scripts/task resume v1-e37-t01-content-editing-decision`). The session records
   the dry-run, corrects scores, sets the ADR to Accepted after your approval, then you create the
   real calendar and sheet (Steps 2 and 3 without `(test)`), store the two addresses in your
   environment and the CI secret store, delete the test resources, and fill in the runbook tables.

## Follow-up work

- **Urgent, out of scope: `wfbschools.org` is not a registered domain.** `whois wfbschools.org` →
  `Domain not found`; `dig @8.8.8.8 MX wfbschools.org` and `NS` return nothing. `wfbschools.com`
  has Google MX records. The site publishes `charles.clark@wfbschools.org` as the contact address in
  seven places (`site/content/site.yaml:44`, `pages/contact.md:11`, `pages/coaches.md:17`,
  `pages/join.md:25,52`, `faq.yaml:32,50`), and the publishing policy gives it as the address for
  removal requests (`docs/policies/website-publishing.md:529`). Mail to it bounces, and anyone could
  register the domain and receive parents' messages. It belongs in a hotfix to site content and a
  policy correction (Charlie approves it as the policy's owner) before the
  October 1 parent session. v1-e37-t05's guide uses `@wfbschools.org` as its reply-to too.
- **Reconcile the parent email list with the team identity** (v1-e37-t05 and the operator).
  Buttondown is registered to `charles.clark@wfbschools.com` with no second owner. The runbook's
  "Reconciling the parent email list" section tracks moving it to the team account after t05 merges.
- **v1-e37-t03 image criterion**: see Deviations. Amend if photos stay repository-only.
- **v1-e37-t02**: the calendar conventions (kind prefixes; `Entry deadline:` as "October 9, 2026";
  `Events:` codes `PF`, `LD`, `Policy`; `Travel notes:`) are set by the guide. t02's recorded
  fixtures should use them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

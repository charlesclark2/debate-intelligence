# Session report: v1-e37-t05-parent-email-signup

| | |
|---|---|
| Task | `v1-e37-t05-parent-email-signup` — Parent email updates |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t05-parent-email-signup` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

> **Production signup URL, for the QR code: `https://wfbdebate.com/#email-updates`**
> It lands on the "Email updates for parents and guardians" section, which says in plain words
> that the address goes to Buttondown, and the button there opens `https://buttondown.com/wfbdebate`.
> Recommended over the Buttondown address itself: it keeps working if the list moves to the
> district's tool, and parents see the disclosure the publishing policy requires before they leave
> the site. **It is live only after a production deploy (below); today it is on the dev preview only.**

Parents can now sign up for team email from the home page (directly under the October 1 parent
session) and the contact page. The site's part is one plain link to Buttondown's hosted signup
page, read from `site/content/email-updates.json`. There is no form, no input and no provider
script, so nothing on the site can receive an address. That is proven by a suite that parses the
built export, not by reading the source, and the suite was shown to fail when provider code was
planted in the export. Charlie chose Buttondown from a comparison of four mailing services and the
district's two routes (Skyward, Smore), set the list up himself (double opt-in on, tracking off,
archive disabled), and the activities director has been told. The guide at
`docs/guides/parent-email-updates.md` records all of it, including every place an address exists.

**The phase stays `InProgress`.** Two criteria cannot pass as written: the list has one owner,
not two (a second Buttondown login costs $79 a month), and ac5's "first-names-only" wording
conflicts with the approved policy's rule, which Charlie chose. Both need the PM. ac4 (the live
opt-in loop) is recorded below.

**Merging is not shipping.** There is no deploy workflow. The signup reaches parents only after
this branch is merged into `dev`, `dev` is promoted to `main`, and the operator runs
`scripts/site_deploy.sh prod` from a clean `main`. For the Thursday, October 1, 6:00 PM session
all three have to happen first. See [Operator follow-ups](#operator-follow-ups).

**Look at first:** the coach address was wrong across the site. It published
`charles.clark@wfbschools.org`, but Charlie's address is `charles.clark@wfbschools.com`. At
Charlie's request it is corrected everywhere it is published, and the publishing policy is now
version 1.1 (Deviation 7).

## Plan nodes

The PM asked for the plan's order to be inverted so the steps with human latency ran first. The
section was built while the vendor research ran, the operator setup went out as soon as Charlie
chose, and the guide was written while he did it.

| Node | Status | Notes |
|---|---|---|
| `compare-and-decide` | Done | Comparison of Buttondown, MailerLite, Mailchimp, Kit (and EmailOctopus in brief) from the vendors' own pages, plus the district's Skyward and Smore routes. Charlie chose Buttondown, 2026-09-29 |
| `signup-section` | Done | Built before the setup, with `signupUrl` as a `[[TBD]]` marker that failed the shipped-content gate and a prod build until the real URL arrived; committed once it had |
| `operator-setup` | Done, with one criterion failing as written | Charlie created the list on 2026-09-29 under charles.clark@wfbschools.com. No second owner: see Deviations |
| `verify-and-guide` | Guide done; live check see ac4 | Dev deployed by the operator at `6039193`, smoke check 31/31 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the guide records the channel, the comparison on cost, double opt-in, unsubscribe, ownership and tracking, and Charlie's approval; the activities director told if a mailing service is chosen | PASS | `docs/guides/parent-email-updates.md`, "The channel, and why": a comparison table on all five dimensions plus archive, branding and signup page, every fact from the vendor's own page fetched 2026-09-29. Chosen by Charlie on 2026-09-29 in this session. Randee Drew, Athletics and Activities Director: told and fine with it, as Charlie reported on 2026-09-29 |
| **ac2**: the home and contact pages show an email-updates section whose link comes from site content config, and the built `site/out` has no script tags from the provider's domain | PASS | `pnpm --dir site test tests/email-updates.test.tsx` → 27 passed. `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → clean, then `pnpm --dir site test tests/no-third-party-scripts.test.ts tests/email-updates.test.tsx` → 38 passed, 0 skipped. Deployed dev checked with curl: `/` and `/contact/` each have `id="email-updates"` and one `href="https://buttondown.com/wfbdebate" rel="noopener noreferrer"`, and 0 `script`/`img`/`iframe`/`link`/`form` tags naming Buttondown |
| **ac3**: no site code, workflow or infrastructure receives or stores subscriber addresses; the only data path is visitor browser → provider | PASS | See [How ac3 was proven](#how-ac3-was-proven). Every place an address does exist is named there and in the guide |
| **ac4**: Charlie subscribes a test address through the dev preview, gets the confirmation email, confirms, receives a test update and unsubscribes with one click | Subscribe, confirm and test update: PASS. **One-click unsubscribe: FAIL as written** (header check pending) | Dev deployed at `6039193`, then redeployed at `aa4d183`; smoke check 31/31 both times. Charlie subscribed charles.clark@wfbschools.com through `https://dev.wfbdebate.com/#email-updates` and received the published test update (Buttondown sends only to confirmed subscribers). The **footer unsubscribe link took two clicks**: it opened a page with an "Are you sure?" dialog and a reason survey (screenshot, 2026-09-30). After that, Buttondown → Subscribers showed the address as **Unsubscribed** (screenshot). Whether the `List-Unsubscribe` header that mail apps show as their own Unsubscribe button is true one-click (RFC 8058 `List-Unsubscribe-Post`) is not stated in Buttondown's docs and is being checked from the test email's raw headers. The site copy no longer says "one click" (`faa6642`) |
| **ac5**: the guide explains how a coach sends an update, the no-student-contact-info and first-names-only rules from the publishing policy, and who owns the list | FAIL as written / PASS as amended | "How to send an update", "What may not go in an email about students" and "Who owns the list". The names rule written is the **policy's** rule (FIRST LAST (GRADUATION YEAR) with current-season consent, or the reduced form asked for), chosen by Charlie over first names only. The policy has no first-names-only rule. See Deviations |
| `compare-and-decide`: comparison drafted (`docs/guides/parent-email-updates.md` contains "double opt-in") | PASS | `grep -c "double opt-in" docs/guides/parent-email-updates.md` → 1 |
| `compare-and-decide`: Charlie chooses the channel and it is recorded in the guide | PASS | Buttondown, 2026-09-29; the guide's status table and "Why Buttondown" |
| `operator-setup`: double opt-in on, **two owners on a team/district identity**, only the public signup URL shared | FAIL as written | Double opt-in on, tracking off and archive Disabled were confirmed by Charlie on 2026-09-29. Only the signup URL was shared. The identity is a district account (charles.clark@wfbschools.com), but **there is one owner, not two** |
| `signup-section`: email-updates component tests pass (`pnpm --dir site test tests/email-updates.test.tsx`) | PASS | 27 passed |
| `signup-section`: static export builds (`pnpm --dir site build`) | PASS | Dev build clean; prod build (`SITE_ENV=prod`) clean, which is the one the content guard is strict on |
| `signup-section`: built output has no third-party scripts (`pnpm --dir site test tests/no-third-party-scripts.test.ts`) | PASS | Run after a build: 11 passed, 0 skipped, on both the dev and the prod export. Planting a Buttondown `<script src>`, a pixel, an inline loader and a posting form into `out/contact/index.html` made 4 of the 11 fail; restoring the file brought it back to 11 passed |
| `verify-and-guide`: guide covers sending an update (contains "How to send an update") | PASS | `grep -n "^## How to send an update"` → line 166 |
| `verify-and-guide`: double opt-in and unsubscribe verified from the dev preview | PASS for double opt-in and unsubscribe; one-click as ac4 | As ac4 |
| Full site suite (not a spec criterion) | PASS | After a build: `pnpm --dir site test` → 20 files, 744 passed, 0 skipped. `pnpm --dir site lint` and `typecheck` clean. The site pre-commit hook ran all four on commit `6039193` |

### How ac3 was proven

"Nothing receives an address" was checked at each layer an address could pass through, rather
than asserted.

| Layer | What was checked | Result |
|---|---|---|
| Built pages | `no-third-party-scripts.test.ts` parses all 10 exported HTML files and fails on any `form`, `input`, `textarea` or `select` | None anywhere. No page has anywhere to type an address |
| Built pages | The same suite: any element that fetches from another origin (`script`, `link` other than canonical/alternate, `img`, `srcset`, `iframe`, `object`, `embed`, media, `form action`, `formaction`) | None |
| Inline scripts, page payloads (`.txt`), bundles and CSS | Any mention of 16 mailing and school-messaging provider domains, plus the configured host, other than the exact signup URL | None. The signup URL appears only as the link's `href` and in the page payload that carries it |
| The link | `rel="noopener noreferrer"`, same tab, no query string. The site's `Referrer-Policy` is `strict-origin-when-cross-origin` (`infrastructure/modules/static_site/main.tf`) | Buttondown is not told which page the parent came from |
| Hosting | `infrastructure/modules/static_site/main.tf`: no `logging_config`, no real-time log config (ADR-0012 decision 8). The two CloudFront Functions (`site_request.js.tftpl`, `redirect.js.tftpl`) rewrite and redirect only; `grep console.` → none | No request record, and the click to Buttondown never reaches CloudFront anyway |
| Infrastructure | All Terraform resource types listed: S3, CloudFront, ACM, Route 53, KMS, SSO, CloudTrail, budgets, cost anomaly. `grep` for SES, Lambda, API Gateway, SNS, SQS, DynamoDB, Cognito → only CloudFront function associations | Nothing that can receive, send or store email |
| Workflows | `.github/workflows/{ci,back-merge,dev-prerelease,promotion-guard}.yml`: `grep -i` for buttondown, mailchimp, mailerlite, convertkit, subscriber, newsletter, smtp, ses, sendgrid, postmark → none | No workflow touches the list |
| Repository | Only the public signup URL is committed; no API key exists (setup step 7) | |

**Where an address does exist.** Named here so it isn't rounded down, and recorded in the guide:

1. **Buttondown**, which stores the list and sends the emails. That is the one intended data path.
   Its terms say it sells nothing and processes data in the United States.
2. **The list owner**, who can see every subscriber in the Buttondown dashboard.
3. **Charlie's district mailbox**, for any parent who replies to an update, because the reply-to
   is charles.clark@wfbschools.com.
4. **The ac4 test address**, Charlie's own, which stays in Buttondown as an unsubscribed record.
5. **Nowhere else, by rule, not by mechanism.** The guide forbids exporting the list to a
   spreadsheet, drive, the repository or AWS. That rests on people following it; no code
   enforces it.

## Files changed

- `site/content/email-updates.json` (new): provider name, signup URL and copy for the section.
- `site/src/components/EmailUpdates.tsx` (new): the section, one outbound link, no copy of its own.
- `site/src/lib/content.ts`: the loader and schema (https-only URL with no credentials, or a
  `[[TBD]]` marker; `{provider}` the only token; strict fields; house style), and the file added
  to `loadGuardedContent()` so the publishing-policy guard checks it.
- `site/src/app/page.tsx`, `site/src/app/[slug]/page.tsx`: place the section on home and contact.
- `site/tests/email-updates.test.tsx`, `site/tests/no-third-party-scripts.test.ts` (new): the
  node's two named test files.
- `site/README.md`: the new content file, its fields, and how to change provider.
- Address correction (Deviation 7): `site/content/{site.yaml,faq.yaml}`,
  `site/content/pages/{contact,coaches,join}.md`, three test files, and
  `docs/policies/website-publishing.md` (version 1.1).
- `docs/guides/parent-email-updates.md` (new): the guide. `docs/README.md`: its index line.

## Deviations from the spec

1. **ac5 and `verify-and-guide`: the names rule.** The spec asks the guide to explain "the
   no-student-contact-info and first-names-only rules from the publishing policy". The approved
   policy (v1.0, 2026-09-20) has no first-names-only rule. Its rule is
   `FIRST NAME LAST NAME (GRADUATION YEAR)` with current-season consent, and first name only
   only when a family asks. This is the same conflict v1-e36-t01 hit. Charlie was offered three
   options (no names in email, first names only, same as the site) and chose **same as the
   site**. The guide says so, and adds the email-specific points: there is no build guard on an
   email, so the check against the allowlist is done by hand, and a sent email cannot be recalled.
   **The PM needs to amend ac5's wording.**
2. **`operator-setup`: one owner, not two.** Buttondown's Teams feature is Professional-plan only
   (+$79 a month, confirmed on buttondown.com/pricing and docs.buttondown.com/teams). The list is on
   a district account, so it is not a coach's personal account, which the spec forbids. But it
   has no second owner. The guide records this as a known gap and three ways to close it. Choosing
   MailerLite would have given a free second seat, at the cost of click tracking that cannot be
   turned off; Charlie chose Buttondown with that trade-off in view.
3. **Paths outside `constraints.packages`.** The spec lists `site/components`, `site/content` and
   `site/tests`, but the site's code lives under `site/src/`. The component is in
   `site/src/components/`, and placing it needed `site/src/app/page.tsx`,
   `site/src/app/[slug]/page.tsx` and the loader in `site/src/lib/content.ts`. `site/README.md`
   and `docs/README.md` were updated because the working agreements require new docs and content
   files to be indexed.
4. **Not linked from `docs/guides/coach-website-editing.md`.** The `verify-and-guide` node asks
   for that link, but the file does not exist yet: it is `v1-e37-t01`'s output, and that task is
   `Pending`. The guide is indexed in `docs/README.md` instead. t01 should add the link when it
   writes the file.
5. **No CSP change.** The spec's CSP `form-action` entry applies "only if a form is used". A link
   was used, so `form-action 'self'` stays as it is and nothing in `infrastructure/` changed. A
   posting form would also have fallen foul of pre-publication checklist 10, which allows no form
   or input.
6. **Config file format.** It is JSON, as the spec names it, although the site's other content
   files are YAML. JSON has no comments, so its fields are documented in `site/README.md`.

7. **The coach address correction, outside this task's scope, at Charlie's request.** On
   2026-09-29 Charlie confirmed that his address is `charles.clark@wfbschools.com`, not the
   `charles.clark@wfbschools.org` the site published. On 2026-09-30 he asked for every instance to
   be fixed. Changed:
   - `site/content/site.yaml` (the email allowlist);
   - `site/content/pages/{contact,coaches,join}.md` and `site/content/faq.yaml`;
   - the tests that pin the address or use a plausible district address
     (`contact.test.ts`, `content-policy.test.ts`, one comment in `faq.test.tsx`);
   - the guide;
   - `docs/policies/website-publishing.md`, bumped to **version 1.1** as a correction with no rule
     changed. The policy's change control requires a re-recorded approval, and Charlie's instruction
     in this session is recorded as that approval, scoped to the address.

   Historical session reports (`v1-e36-t01`, `t04`, `t08`) keep the address as it was at the time.
   The content belongs to `v1-e36-t04` and the policy to `v1-e36-t01`. A prod build is clean, and
   the export has no `.org` address and the `.com` mailto on contact, FAQ, join and coaches.

## Decisions and assumptions

- **Link, not a form.** A link means the site handles nothing. A plain HTML form posting to
  Buttondown would still put an `input` on the site, and the policy's checklist 10 allows none.
- **The provider is named in one field.** Sentences in the config say `{provider}`, so switching
  to the district's tool is an edit to `providerName` and `signupUrl` and a deploy, as the PM asked.
- **Placement.** On the home page, directly under the parent session panel. The QR code is
  scanned at that session, and an existing test pins the academic case as the last band. On the
  contact page it is the last band.
- **Same tab, visibly labelled, no referrer.** Most visitors arrive from a QR code on a phone. The
  button reads "Sign up for email updates (opens Buttondown's site)", because the policy requires
  outbound links to be visibly labelled.
- **Copy states facts, not machinery** (Charlie's standing preference): the address goes to
  Buttondown, not this site; confirmation is by email; every email has a one-click unsubscribe.
- **Archive behaviour differs from Buttondown's docs.** The docs say a Disabled archive returns
  404. On this account `/wfbdebate/archive` returns 302 to the signup page, as Charlie and a curl
  check both found on 2026-09-29. ac4's step 5 checks a sent email's own URL for the same reason.
- **Research method.** A background agent collected vendor facts with verbatim quotes and saved
  the pages. The facts the decision turned on were rechecked against those pages or fetched again:
  Buttondown's teams restriction, 100-subscriber free tier, default-off tracking, default double
  opt-in and public-by-default archive; MailerLite's always-on click tracking and 250-subscriber
  cap. One search result claiming the district uses ParentSquare could not be verified and is not
  in the guide.

## Operator follow-ups

**1. Get it to production before Thursday, October 1, 6:00 PM.** The order is the runbook's
(`docs/runbooks/team-website.md`, "The order, every time"). Merge this task's PR into `dev` and
the `dev` → `main` promotion PR. Then deploy from a **dedicated worktree on `main`**, not from the
main checkout, which is the PM session's working directory (about 5 minutes the first time,
including the install and init a new worktree needs):

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees
git -C ../debate-intelligence fetch origin
git -C ../debate-intelligence worktree add "$PWD/prod-deploy" main
cd prod-deploy
git pull --ff-only
git branch --show-current   # expect: main
pnpm --dir site install --frozen-lockfile
aws sso login --sso-session debate
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod init -reconfigure -input=false
scripts/site_deploy.sh prod
uv run scripts/site_smoke.py --env prod --url https://wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
```

If `worktree add` says `main` is already checked out somewhere, run everything from the `cd`
onwards in that checkout instead. Success looks like: `clean, on main, and equal to origin/main.`,
a clean prod build, the syncs, a completed invalidation, then `All N checks passed.` Then open
`https://wfbdebate.com/#email-updates` on a phone and tap through to Buttondown.

**2. Generate the QR code** from `https://wfbdebate.com/#email-updates` (PM).

Already done by the operator during this session: the Buttondown account and list setup;
`terraform init -reconfigure` for `infrastructure/envs/dev` in this worktree; the dev deploy of
`6039193`, with the smoke check at 31/31.

## Follow-up work

1. **A second owner for the list.** Move the Buttondown login to a district role mailbox a second
   coach can read, pay for Teams, or move to the district's tool (guide, "Who owns the list").
   Needs Charlie and possibly district IT.
2. **The district tool question stays open.** Whether a club can have its own opt-in group in
   Skyward, or a team Smore account, is a question for the activities office. If the answer is yes,
   switching is two fields in `site/content/email-updates.json`.
3. **Link the guide from `docs/guides/coach-website-editing.md`** when `v1-e37-t01` writes it.
4. **Smoke check for the section.** `scripts/site_smoke.py` checks the parent session panel but not
   the email-updates section. A check that `/` and `/contact/` carry `id="email-updates"` and the
   configured link would catch a deploy that lost it. That is outside this task's packages; it
   fits the smoke-check rule in `plan_specs/README.md`.
5. **Subscriber count.** Buttondown is free up to 100 subscribers. Check the count before each
   season's first email.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e37-t05-parent-email-signup

| | |
|---|---|
| Task | `v1-e37-t05-parent-email-signup` — Parent email updates |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t05-parent-email-signup` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

> **Buttondown signup URL, for the QR code: `https://buttondown.com/wfbdebate`**
> This is Buttondown's hosted signup page. It is live now and needs no deploy. Checked on
> 2026-09-30: HTTP 200, titled "Whitefish Bay Debate • Buttondown", with an email field and no
> past emails.

> **The coach-address fix to cherry-pick onto a hotfix from `main`:
> `9ca0aef104cfb91a53d00336eb74cf968672952f`**, the first commit on this branch.
> - **What it contains:** eight files. The five site content files (`site.yaml` with the email
>   allowlist, `faq.yaml`, and the `contact`, `coaches` and `join` pages), the allowlist's two test
>   assertions, and the policy's version 1.1 entry. Nothing else.
> - **Checked on a throwaway worktree of `origin/main`:** it applies cleanly, the prod build passes,
>   706 of 706 tests pass, and the export has no `.org` and the `.com` mailto on four pages.

**What was built.** Parents and guardians can sign up for team email from the site:
- **Where:** the home page, directly under the October 1 parent session, and the foot of the
  contact page.
- **How:** one plain link to Buttondown's hosted signup page, read from
  `site/content/email-updates.json`.
- **What the site can receive:** nothing. There is no form, no input and no provider script.
- **How that is proven:** a suite that parses the built export. It failed when provider code was
  planted in the export.

**Buttondown and the live check.** Charlie chose Buttondown from a comparison of four mailing
services and the district's two routes. He set up the list himself: double opt-in on, tracking off,
archive disabled. The activities director has been told. Charlie also ran the subscribe, confirm,
test update and unsubscribe loop from the dev preview. The guide `docs/guides/parent-email-updates.md`
records all of it, including every place an address exists.

**The site section ships on the next promotion, not by Thursday.** The PM moved the QR code to
the Buttondown URL above, so the parent session no longer depends on a deploy. The section stays as
built. It reaches parents on the next `dev` → `main` promotion and a prod deploy
(`scripts/site_deploy.sh prod`). **Until then it is on the dev preview only, and merging alone
does not publish it.**

**The phase stays `InProgress`, and this goes `--partial`.**
- **ac6 is open by design.** ac6 asks that two people can each, independently, recover the list and its data.
  The list is in the interim state the amendment allows: Charlie's district address, with the
  transfer to the ADR-0015 team account committed for the start of the 2027-28 season. ac6 cannot
  fully close until `v1-e37-t01`'s team account exists, and that is blocked on a second coach.
- **Two operator results are still to come:** unsubscribing with the mail app's own button (the
  PM asked for a click, not a header read), and the first subscriber export. They are marked
  PENDING below.

**About the spec amendment.** ac5 and ac6 come from the PM's PR `specs/t05-ownership-and-student-rules`,
which was not merged when this was written. This branch is **not synced** past it, as the PM asked.
On this branch the spec file still has the old wording until `scripts/task sync` runs after that
PR merges. The criteria below are reported against the amended text.

**Commit SHAs changed on 2026-09-30.** A `scripts/task sync` was run before the PM's "do not sync
yet" arrived. It was undone: the branch was put back on its original base, with the address fix
moved to the front. The final tree is byte-identical to before (`git diff` between the old and new
heads is empty). The dev preview's `version.json` names the pre-restructure commits:

| Deployed as | Same content as |
|---|---|
| `6039193` | `c02cb72` |
| `aa4d183` | `e1ea678` |

## Plan nodes

The PM asked for the plan's order to be inverted so the steps with human latency ran first. The
section was built while the vendor research ran, the operator setup went out as soon as Charlie
chose, and the guide was written while he did it.

| Node | Status | Notes |
|---|---|---|
| `compare-and-decide` | Done | Buttondown, MailerLite, Mailchimp, Kit (and EmailOctopus in brief) from the vendors' own pages, plus the district's Skyward and Smore routes. Charlie chose Buttondown, 2026-09-29 |
| `signup-section` | Done | Built before the setup with `signupUrl` as a `[[TBD]]` marker, which failed the shipped-content gate and a prod build until the real URL arrived |
| `operator-setup` | Done; its ac6 criterion is in the interim state | Charlie created the list on 2026-09-29 under charles.clark@wfbschools.com |
| `verify-and-guide` | Done except the mail-app unsubscribe click | Two dev deploys by the operator, smoke check 31/31 both times. The link from `coach-website-editing.md` waits for the sync (Deviation 4) |

## Acceptance criteria

Reported against the spec as amended in the PM's PR.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the guide records the channel, the comparison on cost, double opt-in, unsubscribe, ownership and tracking, and Charlie's approval; the activities director told if a mailing service is chosen | PASS | Guide, "The channel, and why": a comparison table on all five dimensions plus archive, branding and signup page, every fact from the vendor's own page, fetched 2026-09-29. Chosen by Charlie on 2026-09-29. Randee Drew, Athletics and Activities Director: told and fine with it, as Charlie reported on 2026-09-29 |
| **ac2**: home and contact pages show an email-updates section whose link comes from site content config, and the built `site/out` has no script tags from the provider's domain | PASS | `pnpm --dir site test tests/email-updates.test.tsx` → 27 passed. `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → clean, then `pnpm --dir site test tests/no-third-party-scripts.test.ts tests/email-updates.test.tsx` → 38 passed, 0 skipped. Deployed dev, checked with curl: `/` and `/contact/` each have `id="email-updates"` and one `href="https://buttondown.com/wfbdebate" rel="noopener noreferrer"`, and 0 `script`/`img`/`iframe`/`link`/`form` tags naming Buttondown |
| **ac3**: no site code, workflow or infrastructure receives or stores subscriber addresses; the only data path is visitor browser → provider | PASS | See [How ac3 was proven](#how-ac3-was-proven). Every place an address does exist is named there, including the monthly export ac6 now requires |
| **ac4**: Charlie subscribes a test address through the dev preview, gets the confirmation email, confirms, receives a test update and unsubscribes with one click | **PENDING** (the one-click click). Everything before it: PASS | On 2026-09-30, Charlie:<br>• subscribed charles.clark@wfbschools.com through `https://dev.wfbdebate.com/#email-updates`;<br>• **received the confirmation email and clicked it** before the test update;<br>• received the test update, whose link pointed straight at `https://wfbdebate.com/`, so click tracking is off.<br>**Footer link:** unsubscribing through it took **two clicks**, an "Are you sure?" dialog with a reason survey (screenshot). Buttondown then showed **Unsubscribed** (screenshot).<br>**Headers:** the email carries `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058). That shows one-click is advertised, not that Buttondown's endpoint answers.<br>**Still to do:** the PM asked for the mail app's own Unsubscribe button to be clicked end to end, then a resubscribe. Result: PENDING.<br>**Not on the web:** the test email's archive address returns 404, and `/wfbdebate/rss` has 0 items (curl, 2026-09-30) |
| **ac5** (amended): the guide explains how a coach sends an update, the student rules as `docs/policies/website-publishing.md` states them (cited, never restated), and who owns the list | PASS | Guide, "How to send an update" (step by step, plus a before-every-send list whose first item is the policy's checklist items 1 to 7); "What may not go in an email about students", a table pointing at the policy's Students, published-names allowlist, Photos and media consent, Results and awards and Pre-publication checklist sections, plus only what is specific to email; "Who owns the list". `grep -n "FIRST NAME\|Jordan Rivera\|Students 6" docs/guides/parent-email-updates.md` → none, so no policy rule is copied |
| **ac6** (new): at least two people can independently regain control of the list and its subscriber data, and the recovery path has been tested | **NOT MET, interim state as ac6 allows** | Guide, "Who owns the list": a status line per element.<br>• **Registered to the team identity:** no.<br>• **Mailbox reachable by two people:** no.<br>• **Credentials a second person can retrieve:** no.<br>• **Recovery walked by someone other than Charlie:** not yet.<br>• **Periodic export held by the team:** monthly, started in an interim location. First export: PENDING.<br>The interim state is recorded with the dated commitment ac6 requires: transfer to the ADR-0015 team account **by the start of the 2027-28 season** (Charlie, 2026-09-30). **It cannot fully close until `v1-e37-t01`'s team account exists, which is blocked on a second coach** |
| `compare-and-decide`: comparison drafted (guide contains "double opt-in") | PASS | `grep -c "double opt-in" docs/guides/parent-email-updates.md` → 1 or more |
| `compare-and-decide`: Charlie chooses the channel and it is recorded | PASS | Buttondown, 2026-09-29; the guide's status table and "Why Buttondown" |
| `operator-setup` (amended): double opt-in on, the list meets ac6's recovery requirement, only the public signup URL shared | Double opt-in and URL: PASS. Recovery: as ac6 | Double opt-in on, tracking off and archive Disabled were confirmed by Charlie on 2026-09-29, and only `https://buttondown.com/wfbdebate` was shared |
| `signup-section`: email-updates component tests pass | PASS | `pnpm --dir site test tests/email-updates.test.tsx` → 27 passed |
| `signup-section`: static export builds | PASS | Dev build clean; prod build (`SITE_ENV=prod`) clean, which is the one the content guard is strict on |
| `signup-section`: built output has no third-party scripts | PASS | `pnpm --dir site test tests/no-third-party-scripts.test.ts` after a build → 11 passed, 0 skipped, on the dev and the prod export. Planting a Buttondown `<script src>`, a pixel, an inline loader and a posting form in `out/contact/index.html` made 4 of the 11 fail; restoring the file brought it back to 11 |
| `verify-and-guide`: guide covers sending an update | PASS | `grep -n "^## How to send an update" docs/guides/parent-email-updates.md` → found |
| `verify-and-guide`: double opt-in and unsubscribe verified from the dev preview | As ac4 | |
| Full site suite (not a spec criterion) | PASS | After a build: `pnpm --dir site test` → 20 files, 744 passed, 0 skipped; lint and typecheck clean. The site pre-commit hook runs all four on every commit touching `site/` |

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
4. **The monthly subscriber export**, required by ac6: one CSV file in a private Drive folder
   (Charlie's district Drive until the team account exists), the latest only. This is a deliberate
   second copy of every address, so the list survives losing the Buttondown account. It is outside
   the platform, and the guide sets where it lives and how it is handled.
5. **The ac4 test address**, Charlie's own, on the list.
6. **Nowhere else, by rule, not by mechanism.** The guide forbids putting addresses in the
   repository, AWS, the site, any other spreadsheet or drive, or an attachment. That rests on
   people following it; no code enforces it.

## Files changed

- **The address fix, `9ca0aef`** (for the hotfix):
  - `site/content/site.yaml` and `site/content/faq.yaml`;
  - `site/content/pages/contact.md`, `coaches.md` and `join.md`;
  - `site/tests/contact.test.ts` and `site/tests/content-policy.test.ts`, the allowlist assertions;
  - `docs/policies/website-publishing.md`, version 1.1.
- `site/content/email-updates.json` (new): provider name, signup URL and copy for the section.
- `site/src/components/EmailUpdates.tsx` (new): the section, one outbound link, no copy of its own.
- `site/src/lib/content.ts`: the loader and schema, and the file added to `loadGuardedContent()`
  so the publishing-policy guard checks it. The schema allows only an https URL with no credentials,
  or a `[[TBD]]` marker; `{provider}` is the only token; fields are strict; house style applies.
- `site/src/app/page.tsx`, `site/src/app/[slug]/page.tsx`: place the section on home and contact.
- `site/tests/email-updates.test.tsx`, `site/tests/no-third-party-scripts.test.ts` (new): the
  node's two named test files.
- `site/README.md`: the new content file, its fields, and how to change provider.
- `docs/guides/parent-email-updates.md` (new): the guide. `docs/README.md`: its index line.
- `13a1e34`: the remaining `wfbschools.org` mentions in the guide, two invented test addresses and
  a test comment, kept out of the hotfix commit as asked.

## Deviations from the spec

1. **The names rule.** Resolved by the PM's amendment: ac5 now cites the policy, and the guide
   cites it section by section instead of restating it. Charlie had chosen the site's rule on
   2026-09-29. **One wording problem in the amended ac5**, for the PM: "…so email and site cannot
   diverge), the rules from the publishing policy, and who owns the list." The second "the rules
   from the publishing policy" is left over from the old text.
2. **Ownership.** "Two owners" is replaced by ac6, which is reported above as open in its
   permitted interim state.
3. **Paths outside `constraints.packages`.** The spec lists `site/components`, `site/content` and
   `site/tests`, but the site's code lives under `site/src/`. The component is in
   `site/src/components/`, and placing it needed `site/src/app/page.tsx`,
   `site/src/app/[slug]/page.tsx` and the loader in `site/src/lib/content.ts`. `site/README.md`
   and `docs/README.md` were updated because the working agreements require new docs and content
   files to be indexed.
4. **Not yet linked from `docs/guides/coach-website-editing.md`.** That file exists on `dev` now
   (`v1-e37-t01` merged as #126), but not on this branch's base, because the branch is not synced.
   The same goes for `docs/runbooks/website-content-accounts.md`, which the guide names as a path
   rather than a link for that reason. After the sync, add one row to the coach guide's "What you
   can change, and where" table pointing at the parent email guide, and turn the runbook path into
   a link.
5. **No CSP change.** The spec's CSP `form-action` entry applies "only if a form is used". A link
   was used, so `form-action 'self'` stays as it is and nothing in `infrastructure/` changed. A
   posting form would also have fallen foul of pre-publication checklist 10, which allows no form
   or input.
6. **Config file format.** JSON, as the spec names it, although the site's other content files are
   YAML. Its fields are documented in `site/README.md`.
7. **The coach address correction, outside this task's scope, at Charlie's request.** Charlie
   confirmed on 2026-09-29 that his address is `charles.clark@wfbschools.com`, and on 2026-09-30
   asked for every published instance to be fixed. It is commit `9ca0aef` (see the top of this
   report). The policy is bumped to **version 1.1** as a correction with no rule changed. Its change
   control requires a re-recorded approval, and Charlie's instruction is recorded as that approval,
   scoped to the address. Historical session reports keep the address as it was at the time.
8. **Transfer date is a season, not a day.** ac6 asks for a "dated commitment". Charlie chose "the
   start of the 2027-28 season", which matches the publishing policy's own next review but is not a
   calendar date. The PM may want a specific day.

## Decisions and assumptions

- **Link, not a form.** A link means the site handles nothing. A plain HTML form posting to
  Buttondown would still put an `input` on the site, and the policy's checklist 10 allows none.
- **The provider is named in one field.** Sentences in the config say `{provider}`, so switching
  to the district's tool is an edit to `providerName` and `signupUrl` and a deploy, as the PM asked.
- **Placement.** On the home page, directly under the parent session panel, and as the last band
  of the contact page. An existing test pins the academic case as the home page's last band.
- **Same tab, visibly labelled, no referrer.** Most visitors arrive from a QR code on a phone. The
  button reads "Sign up for email updates (opens Buttondown's site)", because the policy requires
  outbound links to be visibly labelled.
- **The unsubscribe line in the section was corrected after the live check.** It said "unsubscribe
  with one click"; Buttondown's footer link turned out to take two. It now says every email has a
  link to unsubscribe and parents can leave at any time, which is true by either route.
- **Copy states facts, not machinery** (Charlie's standing preference): the address goes to
  Buttondown, not this site; confirmation is by email; every email has a link to unsubscribe.
- **Archive behaviour differs from Buttondown's docs.** The docs say a Disabled archive returns
  404. On this account `/wfbdebate/archive` returns 302 to the signup page, as Charlie and a curl
  check both found on 2026-09-29. After the test update was sent, its archive address returned 404 and the RSS feed had no items, so sent emails are not on the web either way.
- **Research method.** A background agent collected vendor facts with verbatim quotes and saved
  the pages. The facts the decision turned on were rechecked against those pages or fetched again:
  Buttondown's teams restriction, 100-subscriber free tier, default-off tracking, default double
  opt-in and public-by-default archive; MailerLite's always-on click tracking and 250-subscriber
  cap. One search result claiming the district uses ParentSquare could not be verified and is not
  in the guide.

## Operator follow-ups

1. **PENDING: unsubscribe with the mail app's own button, then resubscribe** (about 10 minutes;
   the steps were given in the session). The result goes in ac4.
2. **PENDING: take the first subscriber export** to a private folder in Charlie's district Drive,
   and delete the download. The date and the menu path go in ac6 and the guide.
3. **Hotfix (PM):** cherry-pick `9ca0aef` onto a hotfix branch from `main` and deploy prod, so the
   corrected coach address is live before the parent handout.
4. **After the PM's spec PR merges:** `scripts/task sync v1-e37-t05-parent-email-signup` from this
   worktree, then the two link fixes in Deviation 4, then the full site suite.
5. **Ship the site section** on the next promotion. Deploy prod from a dedicated worktree on `main`,
   not the main checkout, which is the PM's. A fresh worktree needs the install and the Terraform
   init (`docs/runbooks/team-website.md`):

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

   Success looks like:
   - `clean, on main, and equal to origin/main.`;
   - a clean prod build and a completed invalidation;
   - `All N checks passed.`

Already done by the operator during this session:
- the Buttondown account and list setup;
- `terraform init -reconfigure` for `infrastructure/envs/dev` in this worktree;
- two dev deploys, with the smoke check at 31/31 both times;
- the first opt-in loop.

## Follow-up work

1. **Close ac6:**
   - the team Google account (`v1-e37-t01`, blocked on a second coach);
   - move the Buttondown login to it (runbook, "Reconciling the parent email list");
   - a recovery walk by the second owner;
   - move the monthly export to the team Drive.
2. **The district tool question stays open.** Whether a club can have its own opt-in group in
   Skyward, or a team Smore account, is for the activities office. If yes, switching is two fields in
   `site/content/email-updates.json`.
3. **Smoke check for the section.** `scripts/site_smoke.py` does not check for `id="email-updates"`
   and the configured link on `/` and `/contact/`. It fits the smoke-check rule in
   `plan_specs/README.md`, outside this task's packages.
4. **Subscriber count.** Buttondown is free up to 100 subscribers. Check it before each season's
   first email.
5. **Branding the Buttondown page** (optional, free tier):
   - the square team mark as the icon;
   - `#2E2578` as the accent colour.

   Charlie has already set the description.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

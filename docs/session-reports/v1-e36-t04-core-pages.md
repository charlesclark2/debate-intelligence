# Session report: v1-e36-t04-core-pages

| | |
|---|---|
| Task | `v1-e36-t04-core-pages` — Core pages for parents and students |
| Spec | [`plan_specs/v1/e36-team-website/t04-core-pages.yaml`](../../plan_specs/v1/e36-team-website/t04-core-pages.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t04-core-pages` |
| Session status | COMPLETE |

## Summary

The seven core pages are written and building: home, about, events explained, join, coaches,
parent FAQ and contact, in that navigation order, plus the accessibility statement the scaffold
shipped. The copy was drafted from the team's own intro decks for Policy, Lincoln-Douglas and
Public Forum, shown to Charlie as one block mid-session, and rewritten against his edits; the ten
general parent questions are his answers verbatim, as is the paragraph on a new debater's first
month. Nothing about fees, practice times, travel, transportation or coach credentials was
invented.

The substantive piece of engineering is `site/src/lib/publishing-policy.ts`, the part of
[`docs/policies/website-publishing.md`](../policies/website-publishing.md) that a build can check
by itself. It runs during `next build` and fails a prod build on a non-allowlisted email address,
a phone number, an image with no media-consent entry, a capitalised name whose words nobody has
reviewed, a consent entry from a previous season, an unfilled `[[TBD]]` placeholder, or a
cross-origin script or iframe in the built HTML. All seven modes were verified against real prod
builds, not only unit tests. `content/media-consent.yaml` carries the season and the date checked
per named student and per image; both lists are empty, because **the team has not had its first
practice and no page names or depicts a student**, so no roster page was built.

Two things the PM should look at first: the **one remaining placeholder** (the room for the
October 1 session), which Charlie asked to leave as TBD and which blocks the prod launch by
design; and the **brand asset swap**, which is outside the spec's stated packages and is recorded
as a deviation below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `draft-copy` | Done | Seven pages in `site/content/pages/`. Drafted from `Intro to Policy Debate.pptx`, `Intro to LD Debate.pptx` and `Intro to PFD.pptx`, shown to Charlie as one block, then revised: "club" not "class" on home, the consent sentence removed from about, results and roster dropped entirely, his ten FAQ answers and the first-month paragraph used verbatim. |
| `page-routes` | Done | No new route files. `src/app/[slug]/page.tsx` from t03 already generates one route per content file, so the pages exist by existing. See deviation 1. |
| `contact-and-login-flag` | Done | `content/pages/contact.md` is mailto only; the allowlist is `contactEmails` in `content/site.yaml`; `src/lib/feature-flags.ts` holds the `debaterLogin` flag, default off. |
| `policy-and-a11y-checks` | Done | `tests/content-policy.test.ts` (34), `tests/pages-a11y.test.tsx` (42), plus `tests/routes.test.ts` (34), `tests/contact.test.ts` (8) and `tests/login-flag.test.tsx` (10). |
| `charlie-review` | Partly done | Charlie reviewed and edited the copy in session and answered every open question. The phone-width preview walk and the pre-publication checklist tick happen in the PR, which is where the spec puts them. One placeholder remains at his instruction. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — export contains home, about, events, join, coaches, faq and contact, each with its own title and description, reachable from the navigation and listed in `sitemap.xml` | PASS | `SITE_ENV=dev pnpm --dir site build` → exit 0; `find site/out -name index.html` lists `/`, `/about/`, `/events/`, `/join/`, `/coaches/`, `/faq/`, `/contact/`, `/accessibility/`, `/404/`. `pnpm --dir site test routes` → **34 passed**, including one assertion per core page that it is written to `site/out/`, one that every core page links to every other from the navigation on every built page, one that all seven appear in the built `sitemap.xml`, and one that no two pages share a `<title>` or meta description. `cat site/out/sitemap.xml` shows all eight published routes in navigation order. |
| ac2 — events page explains Policy, LD and PF for a parent with no background (format, speech order, cross-examination, prep time, judging); FAQ answers travel, costs, time commitment and parent judging from Charlie's facts only | PASS | `site/content/pages/events.md` has a section per event giving speakers per side, round length, every speech with its time and job, cross-examination, prep time, plus "What the judge does" (flow, ballot, reason for decision, speaker points) and "What a tournament day looks like". Facts traced to the three intro decks. `site/content/pages/faq.md` has 16 questions: judging, time commitment, costs and financial support, transportation, first month, conflicts with other activities, and Charlie's ten. Node criteria: `events.md` contains `Lincoln-Douglas` ✓, `faq.md` contains `judg` ✓. Every fee, practice time, travel and credential statement came from Charlie's message; the only unsupplied fact is marked `[[TBD]]`. |
| ac3 — a content-policy test fails the build on a non-allowlisted email, a phone number, an image with no manifest entry, a placeholder marker, or a cross-origin script or iframe; named students and consented images carry a consent entry with season and date checked; prod fails on a missing entry and warns on a stale one | PASS | `pnpm --dir site test content-policy` → **34 passed**. Verified against real prod builds with the room placeholder temporarily filled (baseline `SITE_ENV=prod SITE_URL=https://wfbdebate.org pnpm --dir site build` → **exit 0**), then one violation appended to `about.md` at a time: non-allowlisted email → **exit 1**, `publishes the email address "boosters@gmail.com", which is not in the allowlist`; phone → **exit 1**, `publishes what looks like a phone number ("414-963-3921")`; unlisted image → **exit 1**, `references the image /photos/state.jpg, which has no entry in content/media-consent.yaml`; unreviewed name → **exit 1**, `names "Jordan Rivera", which has no entry…`; placeholder → **exit 1**, `still has an unfilled placeholder: season fee`. Cross-origin script and iframe are asserted over built HTML in the test suite. Stale consent: a manifest entry dated before 1 August of the current season produces a warning and no error (`the start-of-season check for 2026-27 has not been recorded`); an entry from a previous season attached to a named student is an error. All files restored; `git status` clean afterwards. |
| ac4 — Debater login link absent from the built HTML when the flag is off (default) and present when on; contact page uses only a mailto link | PASS | `pnpm --dir site test contact login-flag` → **18 passed**. Flag off (default build): `grep -c "Debater login" site/out/*/index.html site/out/index.html` → no match on any page, and the suite asserts the label and `href="/app/"` are absent from every built page. Flag on: `SITE_ENV=dev SITE_DEBATER_LOGIN=on pnpm --dir site build` → `href="/app/">Debater login` present in the navigation. `SITE_DEBATER_LOGIN` is on only for the exact value `on`; `off`, `true`, `ON`, empty and unset all fail closed. Contact: `grep -o 'mailto:[^"]*' site/out/contact/index.html` → `mailto:charles.clark@wfbschools.org`; `grep -c "<form\|<input" site/out/contact/index.html` → **0**, and the suite also rejects `<textarea>`, `<select>`, `document.cookie`, `localStorage` and `sessionStorage`. |
| ac5 — axe-core reports no WCAG 2.1 AA violations on every built page **(a)**; Charlie has approved the copy against the pre-publication checklist **(b)** | (a) PASS, (b) NOT RUN | (a) `pnpm --dir site test pages-a11y` → **42 passed**. Two passes: all 8 content pages plus the 404 rendered through the real frame, and all 8 plus the 404 read back from the exported HTML in `site/out/` with the head and `lang` attribute intact, both on the `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa` rule sets → **0 violations**. Also asserted per page: exactly one `<h1>`, no heading level skipped, every `<img>` carries an `alt` attribute, `lang="en"` and a non-empty `<title>`. Colour contrast is asserted against the tokens in `tests/tokens.test.ts` (18 passed), because jsdom has no layout engine. (b) Charlie reviewed and edited the copy in session and answered every open question, but has not yet walked the pages on a phone-width preview or ticked the 16 checklist items. The spec puts that in the PR; it is the PM/Charlie gate, not a session step. |

### Node criteria

| Node criterion | Status | Evidence |
|---|---|---|
| `draft-copy` — `site/content/pages/events.md` contains `Lincoln-Douglas` | PASS | Present, as a full section heading and throughout. |
| `draft-copy` — `site/content/pages/faq.md` contains `judg` | PASS | Present in the parent-judging question and in "How are students evaluated?". |
| `page-routes` — `pnpm --dir site build` | PASS | exit 0, 14 static pages, ~1.5s warm. |
| `page-routes` — `pnpm --dir site test routes` | PASS | 34 passed. |
| `contact-and-login-flag` — `pnpm --dir site test contact login-flag` | PASS | 2 files, 18 passed. |
| `policy-and-a11y-checks` — `pnpm --dir site test content-policy` | PASS | 34 passed. |
| `policy-and-a11y-checks` — `pnpm --dir site test pages-a11y` | PASS | 42 passed. |
| `policy-and-a11y-checks` — `pnpm --dir site lint` | PASS | exit 0, no errors and no warnings. |
| `charlie-review` — `pnpm --dir site test` with no placeholders left | PARTIAL | `pnpm --dir site test` → **Test Files 10 passed, Tests 199 passed**, 2.4s. The suite passes, but **one placeholder remains** (the October 1 room), at Charlie's instruction. A prod build therefore still exits 1 until it is filled; with it filled, a prod build exits 0. See deviation 3. |
| `charlie-review` — Charlie approves the core page copy on a phone-width preview and ticks the pre-publication checklist | NOT RUN | Charlie's gate, in the PR. See the operator follow-up below. |
| Epic criterion — `uv run scripts/validate_specs.py --require-succeeded v1-e36-t04-core-pages` | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases`, exit 0. |

## Files changed

**`site/content/` — the copy and the two reviewed lists**
`pages/home.md`, `pages/about.md`, `pages/events.md`, `pages/join.md`, `pages/coaches.md`,
`pages/faq.md`, `pages/contact.md`: the seven core pages. `site.yaml` gains `contactEmails` (the
email allowlist) and `debaterLoginLabel`, and its footer note now carries the district's required
framing, that the site is run by the team and is not an official district communication.
`media-consent.yaml` is new: the season, the students the site may name, the images it may
publish, the images with nobody in them, and the vocabulary of words allowed inside a capitalised
name.

**`site/src/lib/` — the guard and the flag**
`publishing-policy.ts` is new and is the content guard described above. `media-consent.ts` is new
and loads and validates the manifest, including what "stale" means for a season that runs 1
August to 31 July. `feature-flags.ts` is new and holds the `debaterLogin` flag. `content.ts`
gains `WDCA` to the acronym list and the `[[TBD]]` placeholder marker, which renders as a visible
badge and is reported on every page it survives on.

**`site/src/app/layout.tsx`** runs the guard, because the layout is built for every route, and
appends the Debater login item to the navigation when the flag is on. No new route files: see
deviation 1.

**`site/src/components/`, `site/src/styles/`** — `SiteHeader` uses the transparent navy mark,
`SiteFooter` now carries the white knockout mark on navy instead of standing a text wordmark in
for it, and `components.css` gains the placeholder badge.

**`site/public/brand/`, `site/src/app/icon.png`, `site/src/app/apple-icon.png`,
`site/public/favicon.ico`** — the transparent asset set, replacing the opaque JPEG-recovered
ones. See deviation 2.

**`site/tests/`** — `routes.test.ts`, `contact.test.ts`, `login-flag.test.tsx`,
`content-policy.test.ts`, `pages-a11y.test.tsx` are new; `fixtures/ordering/site.yaml` gains the
two new settings fields.

**`site/README.md`** — the new settings, the content guard table, the placeholder rule, the
rewritten brand-assets section and the note that the suites reading `site/out/` skip themselves
when there is no export.

## Deviations from the spec

1. **No per-page route files.** The `page-routes` node lists `site/src/app/about/page.tsx`,
   `events/page.tsx` and `faq/page.tsx` as outputs. Creating those would collide with
   `site/src/app/[slug]/page.tsx`, which t03 built to generate one route per content file and
   whose own comment says "that is what task v1-e36-t04 does with the core pages". Two route
   definitions for `/about/` is a Next.js error, and hard-coded route files would also reintroduce
   the copy-in-components problem t03 exists to prevent. The node's machine-checkable criteria
   (`build`, `test routes`) both pass. **Suggested spec amendment:** replace those outputs with
   `site/content/pages/*.md`.

2. **Brand assets replaced, which is outside `constraints.packages`.** The spec scopes this task
   to `site/content`, `site/src/app`, `site/src/lib` and `site/tests`. Charlie supplied a
   transparent asset set mid-session and asked for it to be used, including replacing the
   letterboxed favicon, so this touches `site/public/brand/` and `site/src/components/`. It
   resolves open question 6 in the publishing policy and clears the follow-up recorded in the t03
   session report. Flagged rather than silently absorbed; the PM may want it split out.

3. **One placeholder is left in deliberately.** The spec says a build guard blocks a prod build
   that still contains a placeholder, and it does. Charlie asked for the October 1 room to stay
   TBD for now, so `SITE_ENV=prod pnpm --dir site build` exits 1 today. That is the guard working,
   not a defect, but **the prod launch in t05 is blocked until the room is filled**.

4. **No smoke-check node.** Working agreements §5 asks every task changing a user-facing surface
   to add or update its checks for `validate-dev`. This task's plan has no such node. The epic
   assigns the site's smoke checks (HTTP 200, HTTPS redirect, security headers) to `t05`, so
   nothing is missing overall, but the node is absent from this spec.

## Decisions and assumptions

- **The name guard reviews words, not phrases.** Flagging "First Last" runs is only as good as
  what it excuses. An allowlist of whole phrases would have to list "Email Coach Clark",
  "Whitefish Bay High School Debate Team" and every other combination the copy grows into. The
  manifest therefore lists the **words** that may appear inside a capitalised name, so an
  unreviewed word anywhere in a phrase trips the guard while ordinary prose stays quiet. The full
  published-names allowlist, covering opponent schools and tournaments, is `v1-e37-t03`; the
  policy assigns it there.
- **The guard runs from `layout.tsx`.** It is the one module Next builds for every route, so a
  prod build cannot export a page without it having run. Findings are deduplicated per process,
  because Next builds the layout once per route across several workers.
- **Placeholders render, rather than being stripped.** A `[[TBD]]` becomes a visible badge on the
  dev preview. That is how the gaps get found during review; a prod build never reaches the
  rendering, because the guard has already failed it.
- **The accessibility suite runs twice.** Rendering through the frame always works, including in
  CI where `test` runs before `build`. Reading `site/out/` is what the criterion is really about,
  because it covers the head, `lang` and Next's own markup. The built pass skips itself when
  there is no export rather than failing.
- **Results and a roster were dropped.** The draft carried last season's team-level results.
  Charlie asked for neither those nor a roster page yet. Officers, captains and short bios are
  planned but not yet decided, so nothing was left as a stub.
- **The Remind group code is plain text.** No link and no vendor script, which keeps it clear of
  the third-party rules in the policy, and the guard is tested not to mistake `@debatewfb` for an
  email address.
- **`SITE_DEBATER_LOGIN_URL` defaults to `/app/`** rather than an external host, because the epic
  says the V2 app mounts under this same domain. No URL was invented.

## Operator follow-ups

Nothing over two minutes. Everything in this task runs in seconds: the full suite is 2.4s and a
build is about 1.5s warm.

**Charlie, before the PR is merged** (this is ac5(b) and the `charlie-review` node criterion):

```bash
pnpm --dir site install      # once per clone, ~3s
pnpm --dir site dev          # http://localhost:3000
```

Read all seven pages at phone width (360px) in the browser's device toolbar, confirm the facts,
and tick the 16 items of the pre-publication checklist in
[`docs/policies/website-publishing.md`](../policies/website-publishing.md#pre-publication-checklist)
in the PR. Items 1, 2, 4, 6 and 17 are trivially satisfied this time round: no page names or
depicts a student.

**Before the prod launch in t05:** fill the October 1 room in
`site/content/pages/home.md` and confirm `SITE_ENV=prod SITE_URL=https://wfbdebate.org pnpm --dir site build`
exits 0. It exits 1 today, on purpose.

## Follow-up work

- **The published-names allowlist** covering opponent schools, tournaments and students in their
  permitted form is `v1-e37-t03`. This task's `permittedNameWords` is the interim vocabulary and
  should be folded into it rather than maintained twice.
- **An SVG asset set** would still beat the PNGs at every size. The transparent PNGs close open
  question 6 in the publishing policy as a practical matter; the PM may want to record that
  against the policy, since amending an approved, version-stamped document is Charlie's call and
  was left alone here.
- **`site/content/pages/accessibility.md` still points people at "the high school office"** for
  accessibility problems, which t03 wrote before there was a contact page. It could point at the
  contact page now. Left alone as t03's copy.
- **Officers, captains and short bios** are wanted later, per Charlie. That is a new page and a
  new set of consent entries, and it needs the allowlist from `v1-e37-t03` first.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- The pages match the facts Charlie supplied, including the practice schedule, the Remind code, the
  school email, the affiliations and the October 1 announcement. No student names, no photos and an
  empty consent manifest, which is what the policy requires while the roster does not exist.
- `publishing-policy.ts` running inside `next build` is the right place for this. A policy that only
  lives in a document drifts; one that fails the production build does not. Verifying each rule
  against real prod builds rather than only unit tests is what makes that credible.
- Both deviations are accepted:
  - No per-page route files: the t03 `[slug]` route already generates them and adding them would
    collide.
  - The brand-asset swap touches `site/public/` and `site/src/components/`, outside the stated
    packages. It was necessary to use the transparent and knockout marks the PM supplied, and it is
    the smaller change compared with leaving a text wordmark in the footer.
- ac5(b) (phone-width walk plus the 16-item checklist) is Charlie's to run at PR time, where the
  spec puts it. Accepting on that basis: if the walk turns something up, it is a follow-up commit on
  this branch before merge, not a new task.
- The `[[TBD]]` room marker correctly fails a prod build. It blocks the t05 launch, not this task.
  The room goes in as a content edit once Charlie has it.

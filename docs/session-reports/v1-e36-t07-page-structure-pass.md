# Session report: v1-e36-t07-page-structure-pass

| | |
|---|---|
| Task | `v1-e36-t07-page-structure-pass` — Scannable structure for the FAQ, events and remaining pages |
| Spec | [`plan_specs/v1/e36-team-website/t07-page-structure-pass.yaml`](../../plan_specs/v1/e36-team-website/t07-page-structure-pass.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t07-page-structure-pass` |
| Session status | COMPLETE |

## Summary

Every page on the site now puts what a visitor came for above what explains it. The parent FAQ is
five topic sections with an in-page index, each of its seventeen questions a native
`<details>`/`<summary>`, and the three most-asked open on arrival. The events page leads with a
comparison: Public Forum, Lincoln-Douglas and Policy as three cards carrying the same four fields
in the same order and the same current resolution, with the full explanations beneath. About,
join, coaches and contact each open with a lead and an at-a-glance block. The header navigation is
now a written-out list in `content/site.yaml` rather than every file in `content/pages/`, so the
accessibility statement has moved to the footer where it belongs, and the link to the page you are
on carries `aria-current`.

The structural work rewrote none of the approved copy; it regrouped it. Charlie then reviewed the
pages on the dev preview four times during the session, and the copy changes he asked for at each
round are in, including a substantial amount of new material he supplied: the live resolutions, the
entry-fee figure, the two Wisconsin divisions, and his own coaching history. All of it is data
under `site/content/`, validated by `src/lib/content.ts`, so a copy edit stays a content edit. The
full list is in **Decisions**.

**The PM should look first at the Deviations section.** Two things went beyond the spec at
Charlie's direction during review: the events cards carry a current topic, and the FAQ gained a
question. Both want the spec amended rather than left implicit.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `structured-content` | Done | `content/faq.yaml` and `content/events.yaml`, with zod schemas, loaders and the existing house-style rules in `src/lib/content.ts`. The Markdown file keeps a page's identity and lead; the YAML beside it keeps the structure. |
| `faq-disclosure` | Done | `src/app/faq/page.tsx`, `src/components/Disclosure.tsx`, `src/styles/disclosure.css`, `tests/faq.test.tsx`. Native disclosure, no script shipped, print block reveals closed panels in both the ways browsers hide them. |
| `events-comparison` | Done | `src/app/events/page.tsx`, `tests/events.test.tsx`. Three cards, four shared fields, detail sections beneath, one column below 64rem. |
| `remaining-pages` | Done | A reusable `lead` and `atAGlance` block in page front matter, rendered by `src/app/[slug]/page.tsx`; `tests/page-structure.test.tsx`. Covers about, join, coaches and contact. |
| `navigation-and-footer` | Done | `primaryNavigation` in `content/site.yaml`, `excludeFromNavigation` in front matter, `buildNavigation()`, footer utility links, `aria-current`; `tests/navigation.test.tsx`. |
| `structure-gates` | Done | `tests/pages-a11y.test.tsx` now renders the real route modules rather than an approximation of them. Full offline gate set below. |

## Acceptance criteria

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac0** Explicit ordered nav, utility pages in the footer, `aria-current`, mobile menu at 390px | PASS, with one deviation | `pnpm --dir site test navigation` → **39 passed**. The nav is six pages, not the seven ac0 enumerates: contact moved to the footer at Charlie's request, which is **deviation 7** below. The nav is `primaryNavigation` in `content/site.yaml`; `navigation.primary.length < pages.length` is asserted, as is that no published page falls out of both lists. Export check: `/accessibility/` and `/contact/` appear in every page's `<footer>` and in no `<header>`. Each page's own nav link carries `aria-current="page"` in the exported HTML; a page outside the nav marks none. 390px: asserted as target sizes (44px on toggle, nav link and footer link), the 48rem breakpoint that decides the menu is a menu at 390px, tab order through every link, and Escape returning focus to the toggle. **The pixel check at 390px is not possible under jsdom** and belongs to v1-e36-t08. |
| **ac1** FAQ grouped into topic sections, native `<details>` with the question in `<summary>`, in-page index, no `role="button"`/`aria-expanded` | PASS | `pnpm --dir site test faq` → **77 passed**. Five sections, one `<details>` per question, the question in an `<h3>` inside the `<summary>`, an index of five in-page links each resolving to a real section id. `main` contains zero `[aria-expanded]` and zero `[role="button"]`, asserted both in the render and in the exported HTML. |
| **ac2** Two or three named most-asked questions `open` in the export; every answer's full text present whether open or closed | PASS | `pnpm --dir site test faq` → **77 passed**. The exported `/faq/index.html` carries 17 `<details>` and exactly 3 with `open` (cost, time, judging). Every sentence over 24 characters of every answer is matched in the exported markup with the React payload stripped out, open or closed. |
| **ac3** Three parallel cards, same four comparison fields, detail beneath; stacks at 390px with no horizontal overflow | PASS | `pnpm --dir site test events` → **79 passed**. The three cards render the same four labels and values in the same order; every field is filled; each field differs across the three, so the comparison says something. The card holds no part of the detail; each links to its own detail section below. 390px: the grid declares one column outside any media query and every multi-column rule is inside a `min-width` query; the field list stacks label above value and declares no fixed width and no `nowrap`. **Again a source-level check, not a pixel one.** |
| **ac4** About, join, coaches and contact open with a summary block before their detail; a test fails a prose-only page | PASS | `pnpm --dir site test page-structure` → **37 passed**. Each of the four has a two-to-six-item at-a-glance block that renders before the detail band. The criterion asks for "a summary **or** at-a-glance block", so the block is what the suite requires of all four and a lead is optional beside it: contact has none, because a page titled Contact whose content is four ways to send an email does not need a paragraph saying so. A page that does carry a lead still has to say something in it. The blunt half: a page in that set whose body has no heading, list or table fails. |
| **ac5** Every question, answer, comparison field and summary item is a validated field in `site/content/`; a file missing a required field fails the build naming that file | PASS | `pnpm --dir site test content` → **59 passed**. Three fixtures prove the failures: `faq-missing-answer` → `content/faq.yaml: invalid FAQ content (...answer...)`; `events-missing-field` → `content/events.yaml: invalid events content (...topicCadence...)`; `faq-everything-open` → the `openByDefault` range rule. Three more prove the navigation failures. `tests/faq.test.tsx` and `tests/events.test.tsx` each scan `src/app/` and `src/components/` and fail if any of that copy appears in a component. |
| **ac6** axe clean on the restructured pages, every `<summary>` keyboard reachable and operable, print stylesheet expands all disclosures, publishing-policy guard reports only the October 1 room placeholder | PASS, with one caveat and one deviation | `pnpm --dir site test pages-a11y` → **42 passed** (axe over every page through the real route module, plus over the exported HTML). FAQ axe is run twice: with the three most-asked open, and again with every disclosure open. Print: the `@media print` block is asserted to reveal the panel both ways, and no rule anywhere in `disclosure.css` hides a panel. Guard: a prod build (`SITE_ENV=prod pnpm --dir site build`) completes, which it only does with zero findings. **Caveat on "operable by keyboard alone":** see Decisions. **Deviation on the placeholder:** see Deviations. |

### Node criteria

| Criterion | Status | Evidence |
|---|---|---|
| FAQ content is grouped data (`site/content/faq.yaml` matching `openByDefault`) | PASS | File exists and contains `openByDefault`: `grep -n openByDefault site/content/faq.yaml` → 4 lines, three of them the field set on the most-asked questions (lines 40, 70, 93) and one the comment above them explaining the rule. |
| Loader validates the new content files and names a bad one (`pnpm --dir site test content`) | PASS | 2 files, **59 passed**. |
| FAQ uses native details, opens the named questions and indexes its topics (`pnpm --dir site test faq`) | PASS | **77 passed**. |
| Events page renders three parallel cards with the same comparison fields (`pnpm --dir site test events`) | PASS | **79 passed**. |
| Every core page leads with a summary block (`pnpm --dir site test page-structure`) | PASS | **37 passed**. |
| Nav lists exactly the configured pages, footer carries the utility links (`pnpm --dir site test navigation`) | PASS | **39 passed**. |
| Restructured pages have no WCAG 2.1 AA violations (`pnpm --dir site test pages-a11y`) | PASS | **42 passed**. |
| Full site suite passes offline (`pnpm --dir site test`) | PASS | **610 passed**, 0 failed, ~5s. No network: `tests/setup.ts` turns any `fetch` into a failure. |
| Static export builds (`pnpm --dir site build`) | PASS | 14 static pages; `/faq` and `/events` are static routes of their own. |
| Lint passes (`pnpm --dir site lint`) | PASS | Clean. `pnpm --dir site typecheck` also clean. |

## Files changed

**`site/content/`** — `faq.yaml` and `events.yaml` are new and hold the copy those two pages
render. `pages/faq.md` and `pages/events.md` keep their identity and lead. `pages/about.md`,
`pages/join.md`, `pages/coaches.md` and `pages/contact.md` gain a `lead` and an `atAGlance` block
in front matter. `site.yaml` gains `primaryNavigation` and `footerNavigationLabel`.
`media-consent.yaml` gains four words to `permittedNameWords` (see Decisions).

**`site/src/lib/`** — `content.ts` carries the new schemas and loaders (FAQ, events, at-a-glance,
navigation), `COMPOSED_SLUGS`, and `guardedHtml`. `publishing-policy.ts` reads `guardedHtml`
instead of `html`, so copy in front matter is guarded like copy in a body.

**`site/src/app/`** — `faq/page.tsx` and `events/page.tsx` are new composed routes; `[slug]/page.tsx`
renders lead, at-a-glance and detail as bands; `layout.tsx` builds both navigation lists and passes
the wider guarded content to the policy check.

**`site/src/components/`** — `Disclosure.tsx` is new. `Section.tsx` accepts an `h1` and an
optional centred header. `SiteNav.tsx` marks the current page. `SiteFooter.tsx` and
`SiteFrame.tsx` carry the utility links.

**`site/src/styles/`** — `disclosure.css` is new (disclosure, topic index, print). `sections.css`
gains the events comparison, the subgrid alignment, the three-across list and the at-a-glance
block. `layout.css` gains the current-page marker and the footer links.

**`site/tests/`** — `faq`, `events`, `page-structure` and `navigation` suites are new; `content`,
`content-policy`, `routes`, `layout`, `design-system` and `pages-a11y` were updated. Six new
fixtures cover the loader and navigation failures. 610 tests, up from 308.

## Deviations from the spec

1. **The events cards carry a current topic, which the spec does not mention.** Charlie asked for
   it during review: parents want to know what is being argued now, and Public Forum and
   Lincoln-Douglas topics roll over through the season. It is rendered as a labelled block
   *outside* the four comparison fields, so ac3's "same four comparison fields" is untouched. It
   is a `currentTopic` field per event in `content/events.yaml`, so updating it is a content edit.
   **The PM should amend the spec to name it.**

2. **The FAQ now has seventeen questions, not the sixteen the spec assumes.** Charlie asked for a
   question on the two Wisconsin divisions (junior varsity and varsity) under Competing. The
   count assertion was replaced with an explicit roster of the sixteen approved questions, so a
   deliberate addition passes while silently losing one of Charlie's still fails.

3. **ac6's "the publishing-policy guard still reports only the October 1 room placeholder" does
   not describe the repository.** There is no `[[TBD]]` marker for the October 1 room: t06
   replaced it with the sentence "The room is not set yet. It will be posted here before the
   session." in `content/home.yaml`. The guard therefore reports **nothing at all** on the shipped
   content, which is stricter than the criterion asks for. A prod build completing is the
   evidence, since it throws on any error. The room is still unfilled as a fact for t08 to
   resolve, but it is not a guard finding and nothing in the build will remind anyone.

4. **`Section` gained an `h1` heading level and an optional centred header; `CardGrid`'s and
   `Card`'s layout is overridden for the events comparison band.** The spec gives component
   *look* to t06 and page *structure* to t07. These are structural: a composed interior page needs
   its title in a band, a heading over a row of three has to sit over the middle of that row, and
   aligning three cards row by row is what makes a comparison a comparison. The shared rules t06
   owns are untouched, the overrides are keyed to the events band by id, and the home page is
   unaffected. Flagging it because it is a judgement call on that boundary.

5. **Copy changed, at Charlie's direction, on every page.** The spec says rewriting the copy is
   out of scope and the constraints forbid changing the facts without Charlie. Charlie supplied or
   approved every change in session across four rounds of review, so the constraint was met, but
   "structure and presentation only" no longer describes what this task did. The coaches page in
   particular is substantially new content. Recorded here rather than buried in commits; see
   **Decisions** for the full list.

6. **`tests/contact.test.ts` was reading the wrong thing.** Its assertions about what the contact
   page publishes read the Markdown body, so when the addresses moved into the at-a-glance block
   they quietly stopped covering them. It now reads `guardedHtml`. Worth the PM knowing, because
   it is the kind of coverage gap that opens silently whenever content moves between a body and
   front matter.

7. **Contact is in the footer, not the primary navigation, which contradicts ac0.** ac0 enumerates
   the nav as "home, about, events, join, coaches, FAQ, contact". Charlie asked in review for
   contact to move to the footer: it is a short page whose whole content is four ways to send an
   email, the coaches page in the nav carries the address already, and a footer is a conventional
   place for a contact link. It is linked from the footer of **every** page and from the coaches
   page, so nothing became harder to find than one scroll. **The PM should amend ac0's list, or
   say the word and it moves back in one line of `content/site.yaml`.** Flagging the trade-off
   plainly: contact is a page some parents will go to the nav looking for.

## Decisions and assumptions

**Copy Charlie supplied or approved during review.** Every one of these came from him in session:

- Wisconsin tournament entry fees are typically between $10 and $20 per tournament (FAQ, cost).
- Awards go to the top teams, with speaker awards, after the rounds (FAQ, tournament).
- The two Wisconsin divisions, junior varsity and varsity, and who belongs in each (new FAQ question).
- The live Public Forum and Lincoln-Douglas resolutions, and the formal Policy resolution.
- Public Forum's "Best for" is no longer "the most common starting point".
- The events page is titled "Debate Events Offered".
- New wording for the FAQ lead and the closing block, replacing "No question is too basic".
- Join drops "open enrollment" and "no tryout": the point a family is really asking about is that
  no experience is needed and the coaching staff readies a new debater for their first rounds.
- The Remind group and its code, `@debatewfb`, now appear in the join summary as well as the body.
- Coach Clark's coaching history: seven schools across Missouri, Kansas and Wisconsin from 2007,
  with the result at each, and what he does away from the team.
- The coaching stipend and the route to financial support left the coaches summary. Neither is a
  fact about who coaches the team, and both are still on the FAQ, where a family thinking about
  money already is.
- Contact lost its lead and the duplicated 24-hour removal line.

**Copy I drafted, which Charlie has not yet seen.** Two leads were rewritten to his brief rather
than to his words, and he should read them before launch: the about lead and the join lead. Both
are built from facts already on the site; neither introduces one. (The contact lead he did see, and
asked for its removal, so contact now has none.)

**Two numbers that disagreed.** The approved coaches copy said "twenty years of coaching
experience"; the history Charlie supplied starts in 2007, which is nineteen seasons. The page now
says "coaching since 2007", because the list underneath makes the arithmetic checkable and a page
should not carry both. The generic "has qualified many students to national tournaments" sentence
was dropped for the same reason: the per-school list says it specifically.

**Copy I derived rather than quoted, and Charlie then approved on the preview.** The comparison
fields had to be compressed to fit a card. `speechPattern` for all three and `bestFor` for
Lincoln-Douglas and Policy are recombinations of sentences already in the approved draft, not new
facts. Each event's bold summary line was dropped from its detail because every fact in it is now
a comparison field.

**"Operable by keyboard alone" is verified in two halves, not one.** jsdom implements a
`<summary>`'s activation behaviour for a click but not for Enter or Space. That is a gap in jsdom,
not in the page: in a browser both keys run that same activation behaviour, and they do so because
the element is a real `<summary>` in a real `<details>`. The suite therefore drives activation by
click, and separately asserts that every summary is a native `<summary>` child of a `<details>`
with no `tabindex` — a `tabindex` being the usual way a hand-rolled accordion loses those keys. The
real key presses belong to the keyboard-only walk in v1-e36-t08.

**Sixteen words were added to `permittedNameWords`.** `Events` and `Offered` (the title-case
heading "Debate Events Offered"); `United` and `States` (the Public Forum resolution); and
`Central`, `Olathe`, `North`, `Neenah`, `Blue`, `Valley`, `West`, `Marquette`, `University`,
`Jefferson`, `Missouri` and `Indiana` (the schools, universities and states in the coaching
history). The unreviewed-name guard reads any run of capitalised words as a possible person, and
its own message names this as the fix for a phrase that is not one. **Every one of these is an
institution or a place that Charlie supplied and reviewed in session; none is a person, and a
student name still never goes in this list.** The PM may want to look at this: sixteen additions in
one task is the largest expansion the allowlist has had, and `North`, `West`, `Blue` and `Valley`
are generic enough to weaken it slightly for future prose. Two other findings were reworded instead
of allowlisted, because they were ordinary sentence starts and allowlisting `Early` and `Contact`
would have blunted the guard for nothing.

**The FAQ and events pages get route modules of their own.** `COMPOSED_SLUGS` keeps the generic
`[slug]` route from generating the same paths, which would be a build error rather than a silent
preference. `tests/routes.test.ts` was updated accordingly: every core page is still reachable,
either from the dynamic segment or from its own `page.tsx`.

**Card alignment uses CSS subgrid, above 64rem only.** Below that the cards stack and there is
nothing to align. A browser without subgrid (older than Chrome 117, Safari 16 or Firefox 71) skips
the `@supports` block and gets the cards as they were: correct, readable, unaligned. The row
arithmetic is recomputed from `EVENT_COMPARISON_FIELDS` in the test, so adding a fifth field fails
a test rather than quietly pushing one row out of line in all three cards.

## Operator follow-ups

None. Every command in this report runs in a few seconds; the whole suite is 5.5s and the build
about 10s, both well inside the CI budget in `docs/process/working-agreements.md` §1.

## Follow-up work

1. **Academic benefits of debate on the home page** (Charlie, during review). He wants the
   academic-benefit material from the intro-to-debate slides on the home page to broadcast what
   debate builds. The home page belongs to t06 and this is new copy from a source outside the
   repository, so it wants its own task rather than a quiet addition here.
2. **The home page's entry-point card still says "What the events are"** and now links to a page
   headed "Debate Events Offered". That card is t06's approved copy, so I left it. Worth aligning
   in t08 or a copy pass.

2b. **Two leads need Charlie's eye before launch.** The about and join leads were drafted to his
   brief in session but he has not read them on the preview. Nothing in them is a new fact; they
   are still someone else's words on his site.
3. **The October 1 room.** Still unfilled, and now *not* flagged by the guard, because t06 wrote it
   as a sentence rather than a `[[TBD]]` marker. t08 owns filling it in; consider making it a
   marker so the build carries the reminder.
4. **Pixel checks at 390px, 768px and 1280px, and the keyboard-only walk**, are asserted here only
   at the source level, because jsdom has no layout engine. They belong to v1-e36-t08 and this
   report is where t08 should start.
5. **`tests/smoke/` has no entry for these pages.** `plan_specs/README.md` asks every task that
   changes a user-facing surface to add or update smoke checks for `validate-dev`. There is no
   `tests/smoke/` suite for the site yet; the deploy smoke check lives in t05's script. Flagging
   so the PM can decide whether t08 or a separate task closes that gap.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Rulings on the three that needed one:**

1. **Current topic on each event card: keep it, spec amended.** Parents want to know what is being
   argued now, and keeping it a content field means Charlie updates it when topics roll over without
   a session. It sits outside the four comparison fields, so ac3 is untouched.
2. **Seventeen questions: accepted.** Replacing a count with an explicit roster of the approved
   sixteen is strictly better — a deliberate addition passes, a silent drop still fails. That is the
   test doing its actual job rather than counting.
3. **Contact in the footer: accepted, spec amended.** Charlie asked for it and the reasoning holds:
   the page is four ways to send one email and the coaches page carries the address. My one
   reservation is that "Contact" in a nav is a convention parents expect, so if anyone reports
   hunting for it, moving it back is one line in site.yaml.

**On the four for information:**

- **The room marker is the important one.** t06 replaced `[[TBD]]` with a sentence, so nothing now
  reminds anyone the room is unset, and the guard being silent is worse than it being strict. t08's
  spec now requires a check that fails a prod build while a required announcement field is empty: a
  room of "TBA" is a decision, an empty one is an oversight.
- **Component-boundary call: accepted.** An h1 level on Section and an events-only grid override are
  structural; t06's shared rules and the home page are untouched.
- **Copy changing on every page: accepted, and the spec now says so.** Four rounds of preview review
  with Charlie supplying or approving each change is the process working, not scope creep. Waiting
  for another task would have shipped copy he had already rejected.
- **The contact test reading the Markdown body: good catch, and the pattern matters more than the
  fix.** A test that asserts on a source the content has moved away from passes for the wrong reason.
  Asserting on rendered output is the right default for content tests.

**The allowlist expansion is the one thing I would not leave as it is.** Sixteen words, with North,
West, Blue and Valley among them, turns a name guard into something closer to a suggestion for future
prose. t08's spec now makes it a phrase allowlist ("North Shore", "Blue Dukes") rather than bare
words. Rewording two findings instead of allowlisting them was the right instinct.

**Carried to t08:** real-width checks at 390px, the keyboard walk over the disclosures, and the first
tests/smoke/ entries for the site, which no task had picked up. **New task v1-e36-t09** covers the
academic case for debate on the home page from the intro-deck material, sourced and approved by
Charlie; it runs after this and can go alongside t08. All amendments are on branch
`specs/site-structure-rulings`.

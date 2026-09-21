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

None of the approved copy was rewritten to achieve any of that; it was regrouped. Charlie reviewed
the FAQ and events pages on the dev preview twice during the session and the changes he asked for
are in, including several new facts he supplied (see **Decisions**). All of it is data under
`site/content/`, validated by `src/lib/content.ts`, so a copy edit stays a content edit.

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
| **ac0** Explicit ordered nav, utility pages in the footer, `aria-current`, mobile menu at 390px | PASS | `pnpm --dir site test navigation` → **40 passed**. The nav is `primaryNavigation` in `content/site.yaml`; `navigation.primary.length < pages.length` is asserted, as is that no published page falls out of both lists. Export check: `/accessibility/` appears in every page's `<footer>` and in no `<header>`. Each page's own nav link carries `aria-current="page"` in the exported HTML; the accessibility page marks none. 390px: asserted as target sizes (44px on toggle, nav link and footer link), the 48rem breakpoint that decides the menu is a menu at 390px, tab order through all seven links, and Escape returning focus to the toggle. **The pixel check at 390px is not possible under jsdom** and belongs to v1-e36-t08. |
| **ac1** FAQ grouped into topic sections, native `<details>` with the question in `<summary>`, in-page index, no `role="button"`/`aria-expanded` | PASS | `pnpm --dir site test faq` → **77 passed**. Five sections, one `<details>` per question, the question in an `<h3>` inside the `<summary>`, an index of five in-page links each resolving to a real section id. `main` contains zero `[aria-expanded]` and zero `[role="button"]`, asserted both in the render and in the exported HTML. |
| **ac2** Two or three named most-asked questions `open` in the export; every answer's full text present whether open or closed | PASS | `pnpm --dir site test faq` → **77 passed**. The exported `/faq/index.html` carries 17 `<details>` and exactly 3 with `open` (cost, time, judging). Every sentence over 24 characters of every answer is matched in the exported markup with the React payload stripped out, open or closed. |
| **ac3** Three parallel cards, same four comparison fields, detail beneath; stacks at 390px with no horizontal overflow | PASS | `pnpm --dir site test events` → **79 passed**. The three cards render the same four labels and values in the same order; every field is filled; each field differs across the three, so the comparison says something. The card holds no part of the detail; each links to its own detail section below. 390px: the grid declares one column outside any media query and every multi-column rule is inside a `min-width` query; the field list stacks label above value and declares no fixed width and no `nowrap`. **Again a source-level check, not a pixel one.** |
| **ac4** About, join, coaches and contact open with a summary block before their detail; a test fails a prose-only page | PASS | `pnpm --dir site test page-structure` → **37 passed**. Each of the four has a lead and a two-to-six-item at-a-glance block, and the summary band renders before the detail band. The blunt half: a page in that set whose body has no heading, list or table fails. |
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
| Nav lists exactly the configured pages, footer carries the utility links (`pnpm --dir site test navigation`) | PASS | **40 passed**. |
| Restructured pages have no WCAG 2.1 AA violations (`pnpm --dir site test pages-a11y`) | PASS | **42 passed**. |
| Full site suite passes offline (`pnpm --dir site test`) | PASS | **611 passed**, 0 failed, 5.5s. No network: `tests/setup.ts` turns any `fetch` into a failure. |
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
fixtures cover the loader and navigation failures. 611 tests, up from 308.

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

5. **Copy changed, at Charlie's direction.** The spec says the copy is out of scope and the
   constraints forbid changing the facts without Charlie. Charlie supplied or approved every item
   below in session, but the spec still says the copy is fixed, so it is recorded here rather than
   buried in a commit. See **Decisions** for the full list.

## Decisions and assumptions

**Copy Charlie supplied or approved during review.** Every one of these came from him in session:

- Wisconsin tournament entry fees are typically between $10 and $20 per tournament (FAQ, cost).
- Awards go to the top teams, with speaker awards, after the rounds (FAQ, tournament).
- The two Wisconsin divisions, junior varsity and varsity, and who belongs in each (new FAQ question).
- The live Public Forum and Lincoln-Douglas resolutions, and the formal Policy resolution.
- Public Forum's "Best for" is no longer "the most common starting point".
- The events page is titled "Debate Events Offered".
- New wording for the FAQ lead and the closing block, replacing "No question is too basic".

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

**Four words were added to `permittedNameWords`.** `Events` and `Offered` (from the title-case
heading "Debate Events Offered") and `United` and `States` (from the Public Forum resolution). The
unreviewed-name guard reads any run of capitalised words as a possible person, and its own message
names this as the fix for a phrase that is not one. Two other findings were reworded instead of
allowlisted: "Early October" and "Contact Coach Clark" are ordinary sentence starts, and
allowlisting `Early` and `Contact` would blunt the guard for nothing.

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

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

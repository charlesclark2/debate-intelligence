# Session report: v1-e36-t09-home-academic-case

| | |
|---|---|
| Task | `v1-e36-t09-home-academic-case` — Home page: the academic case for debate |
| Spec | [`plan_specs/v1/e36-team-website/t09-home-academic-case.yaml`](../../plan_specs/v1/e36-team-website/t09-home-academic-case.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t09-home-academic-case` |
| Session status | COMPLETE |

## Summary

The home page now closes with an academic-case band: two research claims, each on a Card with a
visible source line naming the authors, the publication, the year and what was measured. The claims
are the two in the Recommended section of `docs/data/academic-case-sources.md` and nothing else.
The Boston claim quotes the 0.096 standard deviation figure for students already in the top quarter,
not the 0.13 headline, and gives no months-of-learning equivalent. The Houston claim carries its
association-not-causation caveat in the claim body. `homeContentSchema` refuses a claim with no
source. A claim marked `[[TBD: source]]` shows a TBD badge in dev and fails a prod build naming the
claim. A new house rule fails the build, naming file and line, on graduation-rate, dropout or "at
risk" wording anywhere in `content/`. The entry-point cards now carry their destination page titles,
and the loader fails on a card that points nowhere or is mislabelled. Charlie approved the exact
copy and the card labels in-session. Worth checking first: the two Deviations below. Both are
places where the spec's wording has gone out of date since it was written.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Sourced academic-case claims in home.yaml (`sourced-claims-content`) | Done | Two claims, both from the Recommended section of the sources file, which Charlie named as the whole input |
| Schema requiring a source, and the excluded-evidence check (`claim-schema-and-house-rules`) | Done | `claimSourceOrMarkerSchema`, `EXCLUDED_EVIDENCE_PATTERNS`, `assertNoExcludedEvidence`; README house style items 4 to 6 |
| The band on the existing layout kit (`academic-case-band`) | Done | Section (`headerAlign="wide"`) + CardGrid + Card. The source line is a small `SourceLine` component, because Next rejects extra named exports from a page file and the TBD and external-link states needed rendering in tests |
| Entry-point card labels matched to their destination pages (`entry-card-labels`) | Done | Three labels changed; `assertEntryPointsMatchPages` runs in `loadHomeContent` |
| Accessibility, guard and approval gates (`accessibility-and-approval-gates`) | Done | axe clean; guard reports no errors; Charlie approved the copy as written |

## Acceptance criteria

All commands were run from the worktree root. Following the runbook, the prod build came first
(`SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build`, exit 0, about 7.5 s) and
the tests ran after it, so the nine suites that read `site/out/` checked this commit's export.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: the band is built from Section, CardGrid and Card, sits after "what debate builds", and a test fails if its copy is in a component | PASS | `pnpm --dir site test home` → 99 passed. Covers the band's position (`what-debate-builds` then `academic-case`, last on the page), one `.card` per claim inside the band's `.card-grid`, and the band's heading, intro, claim and source strings added to the "not written into a component" sweep |
| Goal ac2: every claim has a visible source line (publication, year, what was measured); a claim without a source fails the build naming home.yaml | PASS | `home` tests check each claim's source line holds the authors, publication, year and measured text. `content` test "fails, naming the file, on a claim with no source" → `content/home.yaml: invalid home content (academicCase.claims.0.source: every claim needs a source …` |
| Goal ac3: `[[TBD: source]]` renders as a visible TBD in dev and fails a prod build naming the claim | PASS | Unit test "fails a prod build, naming the file and the claim" (`content`). Also run for real: the first claim's source was set to the marker and `SITE_ENV=prod … pnpm --dir site build` → exit 1, `content/home.yaml: still has an unfilled placeholder: source for the academic-case claim "Students already doing well still gain"`. `SITE_ENV=dev` build → exit 0, with `class="source-line">Source<!-- -->: <span class="placeholder">TBD</span>` in `out/index.html`. Content restored with `git checkout` and rebuilt for prod afterwards |
| Goal ac4: excluded-evidence wording fails naming file and line; the em-dash and acronym checks still pass over the new copy | PASS | `content` tests cover graduation rate, graduation-rate, dropout, drop-out, at risk and at-risk across yaml and md files, each asserting `content/<file>: line <n> uses "<words>"`. A further test checks the rule runs through `loadGuardedContent` (the build path), and one checks it does not trip on "Graduation is in June … drop off … the risk is low". Em dash and NSDA fixtures on the new claims both fail as expected, and the shipped content passes. `grep -c "—" site/out/index.html` → 0 |
| Goal ac5: each card's label matches its destination title; a card that points nowhere or is mislabelled fails the build | PASS | `home` "each entry-point card … is labelled with the title of the page it opens" (4 cases). `content` tests: `/coaching-staff/` → "…which is not a published page", mislabelled card → `…whose title is "Coaches" (content/pages/coaches.md)`, and a renamed destination page also fails |
| Goal ac6: lint, typecheck, test, build pass offline; axe clean on home; source line is body grey; tokens test still recomputes every pair; guard reports only the room placeholder; organisations added to the permitted list | PASS, see Deviations | build exit 0, `pnpm --dir site lint` exit 0, `typecheck` exit 0, `pnpm --dir site test` → 18 files, 706 passed, none skipped. axe: home sweep in `pages-a11y` and `home`, plus built `out/index.html`, all clean. The source line is `color: var(--color-text-body)` (asserted in `home`), and body grey on the panel tint (6.01:1) is already a row in the tokens contrast table. The guard reports **no** errors: the room is now "To be announced" (Deviation 1). Six phrases were added to `permittedNamePhrases` (Deviation 2) |
| Node: Home content carries an academic-case section (`artifact_exists` home.yaml ∋ `academicCase`) | PASS | `grep -c academicCase site/content/home.yaml` → present |
| Node: Charlie supplied every source in-session (custom) | PASS | Charlie named `docs/data/academic-case-sources.md` as the whole input and its Recommended section as the only allowed claims. Every figure on the page is copied from that file: 0.096 SD, 3,515, 2007-08 to 2016-17, 35,788, 1,145, 109, 0.66, 2012 to 2015. No claim is TBD |
| Node: A sourceless claim and an excluded-evidence claim both fail the loader (`pnpm --dir site test content`) | PASS | 2 files, 97 passed |
| Node: Band renders every claim with its source line, and no copy lives in the component (`pnpm --dir site test home`) | PASS | 99 passed |
| Node: Static export builds with the new band (`pnpm --dir site build`) | PASS | Prod build exit 0; `id="academic-case"` in `site/out/index.html` |
| Node: Every entry-point card is labelled with, and resolves to, its destination page (`pnpm --dir site test home`) | PASS | As above |
| Node: Home page has no WCAG 2.1 AA violations and the content guard finds only the room placeholder (`pnpm --dir site test pages-a11y`) | PASS | 43 passed, including the new "home page sweep covers the academic case band". The guard part is in `content-policy`, where "breaks no rule" expects `[]` and passes |
| Node: Full site suite passes offline (`pnpm --dir site test`) | PASS | 706 passed |
| Node: Lint passes | PASS | exit 0 |
| Node: Type check passes | PASS | exit 0 |
| Node: Charlie approved the exact copy and the source list (custom) | PASS | Charlie was shown the band exactly as it publishes (eyebrow, title, intro, both claims, both source lines) plus the three card-label changes, and answered "Approved as written" on 2026-09-20. This is his sign-off under pre-publication checklist item 16 |
| Band stacks to one column at 390px with no horizontal overflow (node description) | PASS | Operator ran `pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95` against a fresh prod export (2026-09-21 04:47 UTC, Chromium via playwright 1.63.0, Lighthouse 13.5.0, axe-core 4.13.0) and it exited clean: `8 pages clear the floor with axe clean at every width`. Home `/`: performance 96, accessibility 100, best practices 100, SEO 100. No horizontal overflow at 390, 768 or 1280. axe (colour-contrast enabled) found no violations on any page at any width. I reviewed the `home-390.png` and `home-1280.png` screenshots: one card per row at 390 with the source lines wrapping inside the cards, two up at 1280 with both source lines lined up along the bottom |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |

## Files changed

* `site/content/home.yaml`: the new `academicCase` section, and three entry-card titles set to their destination page titles.
* `site/content/media-consent.yaml`: six institution and journal phrases the sources name, added to `permittedNamePhrases`.
* `site/src/lib/content.ts`: `claimSourceSchema` / `claimSourceOrMarkerSchema` (https-only links; a missing or incomplete source says which fields are missing), the `academicCase` schema (1 to 5 claims; `externalLinkNote` required once a source links out), per-claim placeholder notes, `assertEntryPointsMatchPages`, and `EXCLUDED_EVIDENCE_PATTERNS` / `assertNoExcludedEvidence`, which runs from `loadGuardedContent` on every build.
* `site/src/app/page.tsx`, `site/src/components/SourceLine.tsx`: the band. `SourceLine` holds no copy. It is not a new layout primitive, only the line inside a Card.
* `site/src/styles/sections.css`: `.source-line` (body grey, small, hairline above, wraps anywhere) and a claim-body margin scoped to `#academic-case`.
* `site/tests/home.test.tsx`, `site/tests/content.test.ts`, `site/tests/pages-a11y.test.tsx`: the tests above. The loader failure cases copy the real `content/` into a temp dir and break one thing each, so no new fixture directories were needed.
* `site/README.md`: house style items 4 (excluded evidence), 5 (every research claim carries its source) and 6 (entry-card labels).
* `plan_specs/v1/e36-team-website/t09-home-academic-case.yaml`: Goal phase set to Succeeded.

## Deviations from the spec

1. **"The publishing-policy guard reports only the October 1 room placeholder" (ac6 and the last
   node) is out of date.** Since t08 the room carries the value "To be announced", and
   `tests/content-policy.test.ts` already expects the guard to report **no** errors. The honest
   version of the criterion holds: the new band adds no finding and the guard's error list is
   empty. The PM may want to reword ac6 to "reports no errors".
2. **`permittedNameWords` is now `permittedNamePhrases`.** The t07 review changed the list from
   words to phrases. The new entries are phrases: Boston Public Schools, Houston Independent School
   District, English Language Arts, and the journal-name fragments Educational Evaluation, Policy
   Analysis and Educational Research (the guard splits these at a lower-case "and", as it does for
   National Speech / Debate Association).
3. **ac2 says "a source object on every claim".** The schema also accepts the bare string
   `[[TBD: source]]` in place of the object, because ac3 requires that marker to be writable and
   to fail only a prod build. Anything else, a missing key or free text included, fails the loader.

## Decisions and assumptions

* **No source links.** The source object supports an optional https `href`, but neither claim has
  one: the approved sources file gives no URL, and adding a DOI from memory would be a
  recalled citation. The "leaves the team site" note (`externalLinkNote`) is in content and is
  tested through `SourceLine`, ready for when Charlie supplies a link.
* **"109 points".** Taken as written from the approved sources file, which records it as the sum of
  the two section gains (52.43 + 57.05 = 109.48). Charlie was shown this in the sign-off question.
* **SAT is not expanded.** The SAT's name no longer stands for anything, so there is nothing to
  spell out and it is not added to `ACRONYM_EXPANSIONS`. "Grade point average" and "standard
  deviations" are written in full, and so is English Language Arts.
* **Wording the 0.096 figure.** Following Charlie's direction, the claim says in words that
  the gains were largest for students who had been behind and that top-quarter students still
  gained, with the figure attached. No years-of-learning conversion is given. I think this
  reads acceptably for parents; the intro's line that the studies come from large city districts
  does the rest of the calibrating.
* **The "what debate builds" band is unchanged.** It gains no citations and is not merged
  with the new band. Whether to fold the two together is left to Charlie, as the spec says.
* **Band tone.** Plain (white) with the tinted Cards, following the plain "what debate builds" band,
  so the page does not end on a second tinted band. The existing hairline separates the two.
* **The excluded-evidence scan includes comments.** A YAML comment is where a sentence sits before
  someone moves it into copy. The new comments in `home.yaml` refer to the rule without using the
  words. Plain "drop out" (the verb) is deliberately not matched, so an FAQ answer about leaving a
  tournament is not blocked. The spec's list (graduation rate, dropout, drop-out, at risk) is
  matched exactly, with hyphenated and plural forms.
* `pnpm install --frozen-lockfile --offline` was run once in the worktree (3.6 s, from the local store) because `node_modules` was absent.

## Operator follow-ups

Done. The browser QA run above was handed to the operator and came back clean. My first hand-off
left out the one-time tools install that every new worktree needs
(`site/scripts/visual-qa-tools/node_modules` lives in each worktree, while Chromium is cached per
machine). The complete sequence, as run:

```bash
pnpm --dir site/scripts/visual-qa-tools install
pnpm --dir site/scripts/visual-qa-tools exec playwright install chromium
SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
```

The screenshots in `site/qa-artifacts/` are git-ignored and were not committed. `/contact/` scored 88 on
performance. Performance has no floor, it scored 88 in the same run, and this task did not change that page.

## Follow-up work

* Reword t09 ac6 (and the last node's criterion name) from "reports only the October 1 room
  placeholder" to "reports no errors", and `permittedNameWords` to `permittedNamePhrases`
  (PM, spec edit).
* If Charlie gets the Allen et al. (1999) PDF, that claim can be revisited through
  `docs/data/academic-case-sources.md` first, then added here as a third card (v1-e36 or a
  later content task).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

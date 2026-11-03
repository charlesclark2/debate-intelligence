# Session report: v1-e37-t15-news-in-the-header-and-the-footer

| | |
|---|---|
| Task | `v1-e37-t15-news-in-the-header-and-the-footer` — News is in the header navigation and stays in the footer |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t15-news-in-the-header-and-the-footer.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t15-news-in-the-header-and-the-footer.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t15-news-in-the-header-and-the-footer` |
| Session status | COMPLETE |

## Summary

News is now the sixth item in the header, after Results and before Join, and it stays in the
footer of every page. `content/site.yaml` gains a short list, `alwaysInFooter: [news]`, naming the
pages the footer keeps when the header carries them too. `buildNavigation` validates it like
`primaryNavigation` (an unknown slug or a duplicate fails the build, naming it) and adds those
pages back to the footer in the footer's usual order, so no other page moves.

**Please look first at the header spacing change in `site/src/styles/layout.css`** (Deviations 1).
With nine links, "Parent FAQ" broke over two lines at 768px and at every width from 1024px up,
1280px included. I narrowed the gap between the links. That is a navigation change outside the
ruling's letter, made so that adding News does not break the header.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `news-in-the-header-and-the-footer` (News in both) | Done | site.yaml, `buildNavigation`, the header spacing, tests and three fixtures |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: /news/ is in the header navigation and the footer of every page, the navigation tests hold, and `pnpm --dir site lint`, `typecheck`, `test` and `build` pass offline | PASS | `site/scripts/pre-commit-checks.sh` at `6a76705` (29.6 s, exit 0): lint clean, typecheck clean, `Test Files 28 passed (28) / Tests 1070 passed (1070)`, dev build `recorded 85 exported files`, export checks `Test Files 13 passed (13) / Tests 130 passed (130)`. **Every page:** the new export check "links News from the header and the footer" ran on all 14 HTML files in the export (`index.html`, the nine other pages, `news/index.html`, `404.html`, `404/index.html`, `_not-found/index.html`), listed with `vitest --reporter verbose`. The dev build publishes no announcement pages on its build date, so none are in that list. The layout is shared, so they carry the same header and footer. **Header and footer in the rendered frame:** `announcements.test.tsx` "is in the header and the footer of the rendered frame". **The navigation tests hold:** `navigation.test.tsx`, 36 passed, with the order relations kept as relations. **Offline:** `tests/setup.ts` stubs `fetch` to throw, and the dependencies came from `pnpm --dir site install --frozen-lockfile --offline` (3.7 s, from the local store) |
| Node `news-in-the-header-and-the-footer`: `pnpm --dir site test` | PASS | 1070 passed, as above |

**Red runs.** The 7 new source tests, run against the pre-task `site/src` and `site/content` with
the new tests in place: `7 failed | 102 passed (109)`. All seven are the new ones: the news
relation, the alwaysInFooter footer check, the three fixture tests, and the two /news/ placement
tests. The eighth new test, "moves no other header page into the footer", passed there as it
should: it guards an invariant the old code already met. The export check, against two builds:

| Change to the committed code | Result |
|---|---|
| The pre-task `site.yaml` (News out of the header) | export: `14 failed`, every page "has no News link in its header" |
| `buildNavigation` ignores `alwaysInFooter` | export: `14 failed`, every page "has no News link in its footer"; source: `5 failed` |
| The footer carries every page | source: `3 failed` ("moves no other header page into the footer", both fixture-site builds) |
| No duplicate check on `alwaysInFooter` | source: `1 failed` ("fails when alwaysInFooter lists the same page twice") |
| No unknown-slug check on `alwaysInFooter` | source: `1 failed` ("fails, naming the slug, when alwaysInFooter lists a page that is not published") |
| `alwaysInFooter: []` in site.yaml | source: `3 failed` (both /news/ placement tests, the alwaysInFooter footer check) |
| `news` out of `primaryNavigation` | source: `4 failed` (the two /news/ placement tests, the news relation, the alwaysInFooter check) |

Each mutant was restored from HEAD with `git checkout HEAD --` after its run.

**Before the report:**

* `uv run scripts/affected_tests.py --run`, bounded at 115 s: stopped at the limit at 84% with
  `2444` passed and none failed or skipped, with the machine at load average 15-17. site/ changes
  reach no pytest test (`site/ changed: the site's own pnpm checks test it; pytest does not.`),
  and the 61 files chosen were the always-run and workflow tests. Under the PM's 2026-10-19
  ruling, a run over about two minutes is left to the pull request's CI, with no operator hand-off.
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`
* ruff and pyright: not run. No Python file changed.
* `uv run scripts/validate_specs.py` → `OK: 599 files, 41 epics, 536 tasks, 22 releases`.

## Files changed

* `site/content/site.yaml`: `news` in `primaryNavigation` between `results` and `join`, and the new
  `alwaysInFooter: [news]`, each with the comment saying why.
* `site/src/lib/content.ts`: the `alwaysInFooter` field (optional, defaulting to empty) and its
  validation in `buildNavigation`. The footer is "every published page not in the header, plus the
  ones alwaysInFooter names", in `loadPages` order.
* `site/src/styles/layout.css`: the gap between header links is 0 from 48rem and 0.5rem from 64rem
  (it was 0.25rem and 1rem). See Deviations 1.
* `site/src/components/SiteFooter.tsx`: the comment now says a header page can stay in the footer.
* `site/tests/navigation.test.tsx`: the news relation, the two footer tests, and three fixture tests
  for the new list.
* `site/tests/announcements.test.tsx`: the test that pinned /news/ out of the header now says it is
  in both, and a rendered-frame test finds News in both landmarks.
* `site/tests/export/navigation.export-test.ts`: News in the header and the footer of every
  exported page.
* `site/tests/fixtures/footer-keeps-a-header-page/`, `footer-unknown-page/`, `footer-duplicate/`:
  fixture sites for the three new `buildNavigation` cases. Their expectations are written by hand.

## Deviations from the spec

1. **The header's link spacing changed** (`site/src/styles/layout.css`). The PM's context put "any
   other navigation change" out of scope; this change is a consequence of adding News, not a
   separate one, but it is outside the ruling's letter. Measured in local headless Chrome over the
   DevTools protocol against an export served on 127.0.0.1, the way `v1-e37-t06` measured the
   eighth link:
   * Eight links (the pre-task `site.yaml`): one row with no label broken at all seven widths from
     768 to 1280px.
   * Nine links at the old spacing: "Parent FAQ" broke over two lines at 768, 1024 and 1280px (it
     held at 800 to 1023px). A 0.75rem gap from 64rem still broke it at 1024 to 1440px. The header is capped at 56rem, so from about 900px the bar has the same width at
     every viewport, and from 64rem the links get 8px more padding and a 16px gap.
   * Nine links after the change (gap 0 between 48rem and 64rem, 0.5rem from 64rem): one row, no
     label broken and no sideways scroll at 768, 780, 800, 850, 900, 1000, 1023, 1024, 1100, 1280,
     1440 and 1920px, on `/` and `/news/`. About 22px are spare at 768px and 14px from 1024px. Every
     link stays at least 41px wide and 50px tall. The links' own padding still separates their
     words. Under 48rem the header is the menu button, which this does not touch.

   If the PM prefers not to tighten the bar, the alternatives are a shorter label (for example
   "FAQ" for "Parent FAQ", which is the coach's copy) or dropping a link from the header. A tenth
   link will not fit at either breakpoint without one of those.

## Decisions and assumptions

* **Where News goes** (ruling 1): after Results and before Join. The two readings in the ruling are
  the same slot, because Join follows Results directly. The order reads: what is coming, how it
  went, what the coaches want families to know now, how to join. One relation pins it: News after
  Results and before Join.
* **The footer rule** (ruling 2): a named list in `site.yaml`, as the PM preferred, rather than a
  per-page front-matter flag. Header placement already lives in `site.yaml`, and a flag would split
  one decision across two files. The list only adds pages back to the footer and keeps the footer's
  own order, so News sits where it did before. The exported footer reads Contact, News,
  Accessibility. The field is optional, defaulting to empty, so the fixture sites needed no edit.
* **What the list refuses:** a slug that is not a published page, and a slug listed twice, each
  naming the slug, as `primaryNavigation` does. It does not refuse a page the header doesn't carry,
  because that page is in the footer anyway and listing it changes nothing. Taking News out of the
  header later then needs one edit, not two.
* **No page becomes unreachable:** the footer is still a superset of "every published page not in
  the header". "Leaves no published page out of both lists" still passes, and "moves no other
  header page into the footer" pins the footer to exactly that set plus `alwaysInFooter`.
* **Visual QA and the smoke check** (ruling 4): neither needs a change. `site/scripts/visual-qa.mjs`
  and `scripts/site_smoke.py` walk `sitemap.xml`, and neither reads the navigation. /news/ was
  already in the sitemap. The visual QA run will see the new header at 768 and 1280px.
* **Local install:** the worktree had no `site/node_modules`. I ran
  `pnpm --dir site install --frozen-lockfile --offline` from the local store, so no network call
  and no pnpm update.

## Operator follow-ups

None. This reaches the live site with the next promotion to main, together with `v1-e37-t03`'s ac5.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

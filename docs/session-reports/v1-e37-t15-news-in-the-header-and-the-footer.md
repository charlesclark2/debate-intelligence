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

**Added after the first review, at the PM's ruling of 2026-11-03** (Deviations 2): the PR's CI
failed on `test_container_factories.py`, a debate_cli test that this task's site work does not
touch. The test passed or failed with the order the tests ran in. Its import recorder credited a
build with import statements run inside integrations loading for the first time. It now credits
only the container's own import statements, which is what "wired" means. This is test tooling,
not site work, in its own commit (`6c4c437`). See "The container factory test fix" below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `news-in-the-header-and-the-footer` (News in both) | Done | site.yaml, `buildNavigation`, the header spacing, tests and three fixtures |
| (no node) The container factory test fix, at the PM's ruling | Done | `packages/debate_cli/tests/test_container_factories.py` only; the spec's `constraints.packages` amended in `cd905eb` |

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

## The container factory test fix

**What failed.** CI `test (2)` on this PR (log pasted by the operator):
`FAILED packages/debate_cli/tests/test_container_factories.py::test_every_factory_builds_and_between_them_they_import_every_wired_integration`
with `'debate_core.integrations.discovery.feed_config: discovery_providers() under the test profile built without it'`.
The branch's Python was dev's own (`c862f2c`). The test fails whenever its file runs first in a
fresh process. It passed with the discovery adapters imported before pytest started.

**Why.** The planted break blocks each wired integration in turn and requires a build that
imports it to fail. The recorder credited a build with every import statement run during it,
including those inside a module loading for the first time. In a fresh process, `feeds` and
`google_news_rss` first load during the test profile's `discovery_providers()` build, so their own
imports of `feed_config` credited that build with `feed_config`. With `feed_config` blocked, the
rebuild found both modules already loaded, built without it, and the test reported the break as
uncaught. Whether the test passed depended on whether an earlier test in the same worker had
loaded the adapters. Since `v1-e41-t17`, whole files are dealt to the CI parts, which can put this
always-run file first in a worker.

**The fix** (ruling 2). `recording_integration_imports` credits an import statement only when the
importing frame's module (`globals["__name__"]`) is `debate_cli.container`. Why I chose this:

* **The container, not every debate_cli module.** The ruling said "under debate_cli". Today the
  two are the same, because no other module in `packages/debate_cli/src` imports an integration
  (`git grep`). I matched the container exactly because `wired_integrations` reads only the
  container's source. Its factories also run their imports on every call. A debate_cli helper
  that imported an integration at module level would load once per process, and crediting it
  would bring back the same first-load order dependence.
* **Not preloading the adapters.** Preloading would also stop integrations' own import statements
  being credited, but it needs a list of modules to preload that every new integration must join.
  It would also leave the recorder crediting more than the wiring check reads. The fix keeps the
  test's two checks unchanged: every wired integration is imported by some build, and blocking it
  fails one.

**Red first** (ruling 4), at `9a1723c` before the fix, the file alone in a fresh process:
`.venv/bin/python -m pytest -n 0 -p no:cacheprovider packages/debate_cli/tests/test_container_factories.py`
→ `1 failed, 5 passed`, the same assertion and message as CI.

**Mutants** (ruling 3), each with the file alone at `-n 0`, restored with `git checkout HEAD --`:

| Mutant | Result |
|---|---|
| The recorder credits every import again (`from_the_container = True`) | `1 failed, 5 passed`: `feed_config: discovery_providers() under the test profile built without it`. The fresh-process failure returns |
| `_build_discovery_providers` drops its own `feeds` import and takes `feed_factory` through the `discovery` package attribute that `google_news_rss`'s import sets (a `TYPE_CHECKING` import keeps `feeds` wired) | `1 failed, 5 passed`: "no factory build imports these", `Left contains one more item: 'debate_core.integrations.discovery.feeds'` |
| Crossref wired under `TYPE_CHECKING` only and dropped from the factories map | `1 failed, 5 passed`: "no factory build imports these", `'debate_core.integrations.discovery.crossref'` |

A first try at the second mutant, `_load_topic_feed_lists` taking `load_feed_directory` from
`feed_check`, passed. That is right: `_build_federated_search` imports `feed_config` itself (line
1563), so a container build still imports it.

**Green** (ruling 4), three runs each, after the fix:

* The file alone, `-n 0`: `6 passed` three times (6.28, 5.97, 4.72 s).
* After the discovery adapters are imported (`feeds`, `google_news_rss`, `feed_config` and the rest
  imported in `python -c` before `pytest.main`): `6 passed` three times.
* `-n 4` with random order: no random-order plugin is installed and adding one is a dependency
  change, so a ten-line scratch plugin (not committed) shuffled the collection with a fixed seed,
  the same in every worker. Seeds 11, 2026 and 90210 put the factory test at positions 411, 143
  and 533 of 826, against 4 unshuffled.
  * The file with `packages/debate_core/tests/integrations/discovery`: `826 passed` three times.
    These runs could not have caught the bug: with the old recorder they also pass, because a
    discovery test loads the adapters in each worker first.
  * The file alone: `6 passed` three times. With the old recorder: `1 failed, 5 passed` three
    times. These are the runs that tell the two apart.

**Before the report** (after the fix):

* `site/scripts/pre-commit-checks.sh` at `6c4c437` (25.8 s, exit 0): `Tests 1070 passed (1070)`,
  `recorded 85 exported files`, export checks `Tests 130 passed (130)`.
* `uv run scripts/affected_tests.py` → `68 of 671 test files (10.1%) chosen in 16.7 s from 18
  changed files`. That is the 61 always-run and workflow files from before, plus 7 the test change
  reaches. Those 7 and the fixed file: `225 passed` in 11.3 s. The whole set with `--run`, bounded
  at 115 s: stopped at the limit at 85% with `2592` passed and none failed or skipped, at load
  average 18. As before, the PM's 2026-10-19 ruling leaves the rest to the pull request's CI. The
  earlier run, before the fix: 84%, `2444` passed, none failed. That run never reached the
  factory test in a fresh worker.
* `uv run --frozen ruff format --check packages/debate_cli` → `142 files already formatted`;
  `ruff check` → `All checks passed!`; `uv run --frozen pyright packages/debate_cli` →
  `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
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
* `packages/debate_cli/tests/test_container_factories.py` (own commit `6c4c437`, at the PM's
  ruling): the import recorder credits only `debate_cli.container`'s import statements, with its
  docstring saying why.
* `plan_specs/v1/e37-calendar-and-announcements/t15-news-in-the-header-and-the-footer.yaml`
  (`cd905eb`): `constraints.packages` gains that test file, with a comment naming the ruling.

## Deviations from the spec

1. **The header's link spacing changed** (`site/src/styles/layout.css`). The PM's context put "any
   other navigation change" out of scope; this change is a consequence of adding News, not a
   separate one, but it is outside the ruling's letter. Measured in local headless Chrome over the
   DevTools protocol against an export served on 127.0.0.1, the way `v1-e37-t06` measured the
   eighth link:
   * Eight links (the pre-task `site.yaml`): one row with no label broken at all seven widths from
     768 to 1280px.
   * Nine links at the old spacing: "Parent FAQ" broke over two lines at 768, 1024 and 1280px (it
       held at 800 to 1023px). A 0.75rem gap from 64rem still broke it at 1024 to 1440px. The
     header is capped at 56rem, so from about 900px the bar has the same width at every
     viewport, and from 64rem the links get 8px more padding and a 16px gap.
   * Nine links after the change (gap 0 between 48rem and 64rem, 0.5rem from 64rem): one row, no
     label broken and no sideways scroll at 768, 780, 800, 850, 900, 1000, 1023, 1024, 1100, 1280,
     1440 and 1920px, on `/` and `/news/`. About 22px are spare at 768px and 14px from 1024px. Every
     link stays at least 41px wide and 50px tall. The links' own padding still separates their
     words. Under 48rem the header is the menu button, which this does not touch.

   If the PM prefers not to tighten the bar, the alternatives are a shorter label (for example
   "FAQ" for "Parent FAQ", which is the coach's copy) or dropping a link from the header. A tenth
   link will not fit at either breakpoint without one of those.

2. **The container factory test is fixed in this PR** (PM ruling, 2026-11-03, option 2). This is
   test tooling, not site work. It is done here because the promotion to main runs the whole
   selection and would meet the same order-dependent failure at random. The spec's
   `constraints.packages` gains `packages/debate_cli/tests/test_container_factories.py`
   (`cd905eb`), and the fix is its own commit (`6c4c437`). Nothing else outside `site/` changed.

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

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

The coach's decision, built with the smallest rule that moves nothing else, and checked on every
exported page rather than one.

1. **ac1 passes.** News sits after Results and before Join in the header and stays in the footer of
   all 14 exported pages (a new export check); the navigation order tests stay relations; lint,
   typecheck, 1,070 tests, the build and 130 export checks pass offline. The 7 new source tests failed
   first, and the seven planted breaks were each caught.
2. **The footer rule accepted:** `alwaysInFooter` in site.yaml, validated like `primaryNavigation`, only
   adding pages back in the footer's own order, so no other page moves and none can become unreachable.
3. **Deviation 1 accepted.** Tightening the gap between header links is a consequence of the ninth link,
   measured at twelve widths with no label broken and no sideways scroll. Recorded for later: a tenth
   header link will not fit at either breakpoint without a shorter label or dropping a link.
4. **Visual QA and the smoke check** walk the sitemap and need no change; the visual QA at the next deploy
   sees the new header.
5. **Live:** with the next promotion to main, together with v1-e37-t03's ac5.
6. **Closing checks:** the Python affected set (always-run and workflow tests only) reached 84% with no
   failure and is left to `ci`; lint-imports and the specs are clean; no Python changed.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

## PM review (second)

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

The container factory test fix, added at the PM's ruling of 2026-11-03 (option 2), is right and proved
the way that matters: in the order that broke it.

1. **The cause is the one the session named:** the recorder credited a build with imports run inside
   integrations loading for the first time, so the test passed or failed with the order its file ran
   in, and v1-e41-t17's whole-file dealing could put it first in a fresh worker.
2. **The fix keeps the test's purpose:** only `debate_cli.container`'s own import statements are
   credited, which is what `wired_integrations` reads. The two purpose mutants (a factory reaching its
   integration only through another module's import, and an integration wired nowhere) are still
   caught, and the old recorder brings the fresh-process failure back.
3. **Red first** in a fresh process at the start commit (1 failed, 5 passed, the CI message); **green**
   alone, after the adapters are imported, and shuffled, three runs each. The session was right to say
   which runs could tell the two recorders apart.
4. **Deviation 2 accepted:** one test file, its own commit, the spec's packages amended.
5. **Closing checks** after the fix: the site's checks (1,070 tests, 130 export checks), the affected set
   to 85% with no failure, ruff, pyright and lint-imports on debate_cli, and the specs are clean.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`. This is the last
   merge before dev is frozen for the promotion.

## PM note after the promotion (2026-11-03)

Added by the PM. Nothing above is changed, and this is not a review.

Live with promotion #810: the dev preview at `e83c607b` (41 of 41 smoke checks, `/news/` among them,
and read on a phone), then prod from `main` at `3f827613` (41 of 41). News is in the header and the
footer on wfbdebate.com.

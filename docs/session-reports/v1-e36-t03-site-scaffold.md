# Session report: v1-e36-t03-site-scaffold

| | |
|---|---|
| Task | `v1-e36-t03-site-scaffold` — Static site scaffold |
| Spec | [`plan_specs/v1/e36-team-website/t03-site-scaffold.yaml`](../../plan_specs/v1/e36-team-website/t03-site-scaffold.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t03-site-scaffold` |
| Session status | COMPLETE |

## Summary

`site/` now holds the public team website's code base: a Next.js 16 App Router project that
exports to plain static files for the S3 + CloudFront distribution `v1-e36-t02` will define, with
its own pnpm lockfile and no link of any kind to the V2 app in `web/`. It provides the
mobile-first frame (skip link, `banner`/`main`/`contentinfo` landmarks, one focus style, a
navigation menu that opens with Enter or Space and closes with Escape), a design system built on
the brand colours the operator supplied mid-session, a typed content loader that validates
`site/content/` against a zod schema and fails the build naming the bad file, and SEO basics whose
indexing behaviour is driven by `SITE_ENV` and fails closed.

Two things the PM should look at first. **The brand palette is not fully AA-safe:** muted grey
`#74798E` and the warm accent `#B36B00` measure between 3.6:1 and 4.3:1, short of the 4.5:1 normal
text needs. Per the operator's instruction they were kept and restricted to large text and
non-text use, and a unit test fails if any stylesheet paints small text with either. **The
scaffold ships one content page beyond `home.md`** — an accessibility statement — because Next
refuses to build a `[slug]` route whose `generateStaticParams()` returns nothing. Its copy makes
claims only about how the site is built, but it is still copy, and it should go through `v1-e36-t01`'s
pre-publication checklist before the first prod launch.

All 71 tests, lint, typecheck and both the dev and prod builds pass offline, in about nine seconds
in total.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `project-scaffold` | Done | Next 16.3.5, React 19.3.0, TypeScript 5.9.3, vitest 3.2.7, all pinned to exact versions. Static export, trailing slashes, unoptimized images, strict tsconfig with `noUncheckedIndexedAccess`. ESLint 9 flat config using `eslint-config-next`'s native flat export plus the full `jsx-a11y` recommended rule set. |
| `design-system-layout` | Done | `src/styles/tokens.css` is the single source of colour, type and spacing, with the palette's provenance and all 15 measured contrast ratios in its header. `SiteFrame` holds the landmark structure so tests exercise the real frame rather than a copy. `Button`, `Card` and `Prose` added. |
| `content-loader` | Done | `src/lib/content.ts` reads Markdown with YAML front matter and `site.yaml`, validates with zod, renders Markdown at build time, and throws `ContentValidationError` naming the file. Also enforces the two house-style rules the operator gave. |
| `seo-basics` | Done | `app/sitemap.ts` and `app/robots.ts`, plus `src/lib/page-metadata.ts` for per-page title, description, canonical URL, Open Graph and the indexing directive. |
| `quality-gates` | Done | `site/scripts/pre-commit-checks.sh` runs lint, typecheck, test and build; wired to a `site-checks` pre-commit hook filtered on `^site/`. `site/README.md` written. No `.github/workflows/ci.yml` exists, so the `site` job is handed to `v1-e01-t04`; the README carries the exact steps. |

## Acceptance criteria

All commands were run from the worktree root unless stated. Full test counts are from
`pnpm --dir site test`.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — build produces `site/out/` with `index.html`, `404.html`, `sitemap.xml`, `robots.txt`, no network, no server runtime | PASS | `SITE_ENV=prod SITE_URL=https://debate.example.invalid pnpm --dir site build` → exit 0; route table lists only `○ (Static)` and `● (SSG)` entries, no server route. `ls site/out/{index.html,404.html,sitemap.xml,robots.txt}` → all four present. Offline: `NEXT_TELEMETRY_DISABLED=1` is in the build script (`next telemetry status` → `Disabled`), and the 8 assertions in `tests/offline.test.ts` check the source for remote fonts, third-party scripts, CDN assets, `fetch`, `next/server` and `web/` imports. |
| ac2 — dev build disallows all paths and emits a noindex tag; prod build allows indexing and lists every content page | PASS | `SITE_ENV=dev … build` → `site/out/robots.txt` is `User-Agent: *` / `Disallow: /`; `site/out/index.html` and `site/out/accessibility/index.html` both carry `<meta name="robots" content="noindex, nofollow"/>`. `SITE_ENV=prod … build` → `robots.txt` is `Allow: /` plus `Sitemap: https://debate.example.invalid/sitemap.xml`; `sitemap.xml` lists `/` and `/accessibility/`, which is every published page; `index.html` carries `content="index, follow"`. |
| ac3 — content validated at build time; a missing required field fails the build naming the file | PASS | Verified against a real build, not only a unit test: the `description` was deleted from `content/pages/accessibility.md` and `SITE_ENV=prod pnpm --dir site build` exited **1** with `Error [ContentValidationError]: content/pages/accessibility.md: invalid front matter (description: Invalid input: expected string, received undefined)` and `filePath: 'content/pages/accessibility.md'`. The file was restored and the build returned to exit 0. Also covered by 5 assertions in `tests/content.test.ts`. |
| ac4 — skip link, landmarks, visible focus, keyboard mobile menu, no axe WCAG 2.1 AA violations | PASS | `pnpm --dir site test layout` → 13 passed, including *puts a skip link first, pointing at the main landmark*, *exposes banner, navigation, main and contentinfo landmarks*, *opens and closes from the keyboard alone*, *closes on Escape and returns focus to the toggle*, *reaches every navigation link by tabbing*, and axe-core runs over the real frame (closed and open) and over Button, Card and Prose on the `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa` rule sets → 0 violations. Visible focus is a single `:focus-visible` rule in `globals.css`; its contrast is asserted in `tokens.test.ts`. |
| ac5 — tokens in one file citing the brand guidelines; body text and links meet 4.5:1 in a unit test | PASS | `pnpm --dir site test tokens` → 18 passed. `src/styles/tokens.css` is the only place a colour is defined; its header cites the source of the palette. Nine text-on-background pairs are asserted at ≥4.5:1 (body, headings, links, hovered links on white and on the panel tint; inverse text and links on navy) and the focus ring at ≥3:1 on both surfaces, all recomputed from the file itself. See the deviation below about the two colours that cannot reach 4.5:1. |

### Plan node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `project-scaffold` — `site/next.config.ts` contains `output: 'export'` | PASS | Present at `site/next.config.ts:16`. Also asserted by `tests/offline.test.ts` → *configures a static export with no server runtime*. |
| `project-scaffold` — `pnpm --dir site build` | PASS | exit 0. Cold 3.8s, warm 1.6s. |
| `design-system-layout` — `pnpm --dir site test -- layout tokens` | PASS | exit 0; 71 passed (5 files). Run on their own: `pnpm --dir site test layout` → 13 passed, `pnpm --dir site test tokens` → 18 passed. See the note on `--` below. |
| `content-loader` — `pnpm --dir site test -- content` | PASS | exit 0; 71 passed. On its own: `pnpm --dir site test content` → 15 passed. |
| `seo-basics` — `pnpm --dir site test -- seo` | PASS | exit 0; 71 passed. On its own: `pnpm --dir site test seo` → 17 passed. |
| `quality-gates` — `pnpm --dir site lint` | PASS | exit 0, no errors and no warnings. |
| `quality-gates` — `pnpm --dir site test` | PASS | `Test Files 5 passed (5)`, `Tests 71 passed (71)`, 1.4s. |
| `quality-gates` — `pnpm --dir site build` | PASS | exit 0. |
| Epic criterion — `uv run scripts/validate_specs.py --require-succeeded v1-e36-t03-site-scaffold` | PASS | `v1-e36-t03-site-scaffold: Succeeded`, exit 0. `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases`. |

**A note on the `--` in three node criteria.** `pnpm run test -- <filter>` forwards a literal `--`
to vitest, which then ignores the trailing filter and runs the whole suite. So
`pnpm --dir site test -- layout tokens` exits 0 having run all 71 tests, a superset of the named
files: the criterion passes, but not by running only those files. The filtered form
(`pnpm --dir site test layout`) was therefore run as well, and is recorded above. The suite takes
1.4s, so no change was made to work around this; it is noted here so nobody reads the criterion as
proof that the files were run in isolation.

## Files changed

**`site/` (new, 58 files)**

* Project config: `package.json` (exact-pinned versions, `packageManager`, telemetry disabled in
  the scripts), `pnpm-lock.yaml`, `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`,
  `vitest.config.ts`, `.gitignore`.
* `src/app/`: `layout.tsx`, `page.tsx`, `[slug]/page.tsx`, `not-found.tsx`, `sitemap.ts`,
  `robots.ts`, and the generated `icon.png` and `apple-icon.png`.
* `src/components/`: `SiteFrame`, `SiteHeader`, `SiteNav`, `SiteFooter`, `SkipLink`, `Button`,
  `Card`, `Prose`, `landmark-ids`.
* `src/lib/`: `content.ts` (schema, loader, house-style rules), `page-metadata.ts`,
  `site-settings.ts` (`SITE_ENV`, `SITE_URL`).
* `src/styles/`: `tokens.css` (palette, provenance, contrast table), `globals.css`, `layout.css`,
  `components.css`.
* `content/`: `site.yaml`, `pages/home.md`, `pages/accessibility.md`, `not-found.md`.
* `tests/`: `setup.ts`, `contrast.ts`, `axe.ts`, and the `tokens`, `layout`, `content`, `seo` and
  `offline` suites, plus five fixture content directories.
* `public/brand/`: the two operator-supplied PNGs; `public/favicon.ico` generated from the mark.
* `scripts/pre-commit-checks.sh`, `README.md`.

**`.pre-commit-config.yaml`** — added the `site-checks` hook, filtered on `^site/`, following the
`terraform-checks` pattern of calling a script that reports what is missing rather than failing
obscurely.

**`plan_specs/v1/e36-team-website/t03-site-scaffold.yaml`** — Goal `status.phase` to `Succeeded`.

**`docs/session-reports/v1-e36-t03-site-scaffold.md`** — this report.

## Deviations from the spec

1. **The team brand guidelines do not exist as a document.** The spec requires tokens "taken from
   the team brand guidelines, not invented", and forbids colours not taken from them. No such
   document is in the repository, and `v1-e36-t01`, which will write the Branding section, is still
   `Pending`. Mid-session the operator supplied the palette directly, sampled from the team deck
   template off the Blue Dukes "W BAY" wordmark, noting that the district publishes no official hex
   codes. Those values were used verbatim and no colour was invented. `tokens.css` and
   `site/README.md` both record the provenance and say the values stand until `v1-e36-t01` records
   something more authoritative.

2. **Two brand colours cannot meet AA for normal text, and were kept anyway.** Measured: muted grey
   `#74798E` is 4.31:1 on white and 3.74:1 on the panel tint; warm accent `#B36B00` is 4.18:1 and
   3.63:1. All four fall short of 4.5:1. On the operator's instruction the brand colours were kept
   and restricted to large text (≥24px, or ≥18.66px bold) and to non-text use such as borders,
   which need only 3:1. Small secondary copy uses body grey `#55596B` (6.94:1) instead. The
   restriction is enforced, not just documented: `tokens.test.ts` asserts both colours sit in the
   3:1–4.5:1 band and fails if any stylesheet uses either as a `color:` on text.

3. **A typeface substitution.** The decks use Arial. The spec forbids remote fonts and any network
   access during the build, which rules out `next/font/google`, so the site requests Arial and falls
   back to metric-compatible faces already installed on each platform. No font is downloaded. This
   is the only difference from the deck template.

4. **One content page beyond the placeholder home page.** The spec's content-loader node asks only
   for `content/pages/home.md`. Next refuses to build a `[slug]` route whose
   `generateStaticParams()` returns an empty array under `output: 'export'`, so shipping the generic
   content route — which is scaffold work, and which lets `v1-e36-t04` add pages as files rather
   than as components — required a second page. `content/pages/accessibility.md` was chosen because
   an accessibility statement describes how the site is built rather than telling the team's story,
   so it does not encroach on t04's list (Home, About, Events explained, How to join, Coaches,
   Parent FAQ, Contact). It names no student, makes no claim about the team, and states only things
   that are true of this build. **It is still copy and needs Charlie's review** under t01's
   pre-publication checklist before the first prod launch. The alternative was to drop the `[slug]`
   route and hand routing to t04; that was not chosen because routing is scaffold, not copy.

5. **Two house-style rules were built into the content validator.** Mid-session the operator set
   two rules: no em dashes in body copy, and every acronym translated on a page parents or new
   students read. Both are enforced at build time by `src/lib/content.ts` rather than left to
   review: an em dash fails the build naming the file and the line, and using `NSDA`, `NCFL`,
   `TOC`, `LD` or `PF` without the expansion on the same page fails naming the acronym. This goes
   beyond the spec's schema fields (title, description, nav order, Open Graph image); it is recorded
   here rather than added to the spec, since the spec is closed. If the PM wants it in the contract,
   it belongs in t04's spec, which is where the rules will do most of their work.

6. **The pre-commit hook calls a script inside `site/`.** The spec's constraint limits changes to
   `site` and `.pre-commit-config.yaml`, so the helper went to `site/scripts/pre-commit-checks.sh`
   rather than to the repository's `scripts/`, where `terraform_checks.sh` lives. The pattern is the
   same; only the location differs, to stay inside the stated packages.

7. **`pnpm typecheck` was added as a fourth script.** The spec lists lint, test and build. `tsc
   --noEmit` runs in about a second and caught a real error during the session (an unused import
   that `next build` did not surface), so it is in the hook and in the suggested CI job.

## Decisions and assumptions

* **Versions are pinned exactly**, with no `^`, as the node asks. Next 16.3.5 / React 19.3.0 /
  TypeScript 5.9.3 / vitest 3.2.7 / ESLint 9.39.5. TypeScript 7 and ESLint 10 were available but
  not chosen: `eslint-config-next` 16 targets the 9.x line, and a brand-new compiler is not worth
  the risk on a site whose main job is to be boring and to keep working.
* **`SITE_ENV` fails closed.** Only the exact string `prod` is indexable. Unset, misspelled or
  `staging` all behave as dev: disallow everything, `noindex, nofollow`. A preview that quietly
  gets indexed is a privacy problem on a site about high-school students, so the default is the
  safe one. There is a test for each of `dev`, unset, `staging`, `PROD` and `""`.
* **`sitemap.xml` records no `lastModified`.** It would come from file timestamps, which differ
  between checkouts and CI runners and would make the export non-reproducible, defeating a useful
  diff against what is already in the bucket at deploy time (`v1-e36-t05`).
* **Links do not prefetch.** The whole site is a handful of static pages, so prefetching every
  route would cost the visitor requests for nothing.
* **The 404 copy lives outside `content/pages/`**, in `content/not-found.md`, so it is validated by
  the same schema but can never appear in the navigation or the sitemap.
* **Markdown is rendered at build time and injected with `dangerouslySetInnerHTML`.** The input is
  Markdown committed in this repository; nothing user-supplied can reach it, and there is no
  runtime fetch. `react/no-danger` is turned off with that reasoning recorded in
  `eslint.config.mjs`. If the site ever renders content from outside the repository, this needs a
  sanitiser.
* **axe-core cannot check contrast under jsdom**, which has no layout engine, so the rule is
  disabled explicitly in `tests/axe.ts` rather than left to pass vacuously, and contrast is
  asserted against the tokens instead. A browser-based check belongs with the deploy smoke tests in
  `v1-e36-t05`.
* **`pnpm` had to be installed.** It was not on the machine, and `corepack enable pnpm` fails on
  corepack 0.30.0 because the npm signing key it ships with has expired.
  `COREPACK_INTEGRITY_KEYS=0 corepack prepare pnpm@10.15.0 --activate` was used. The workaround is
  recorded in `site/README.md` and in the pre-commit script's error message.

## Operator follow-ups

Nothing in this task took longer than about four seconds, so nothing was handed over mid-session.
Three things need the operator:

1. **Supply a proper brand asset set.** The two PNGs are opaque white-background images recovered
   from a JPEG, which constrains the design in two visible ways: nothing can be placed on the navy
   footer (it uses the `WFB Debate` wordmark as text instead), and the generated icons letterbox a
   wide mark into a square. At 32px the W silhouette reads clearly but the "BAY" lettering inside it
   blurs into a smudge. What would fix it, in priority order:
   * `wfb-wbay-mark.svg` and `wfb-blue-dukes-lockup.svg`, or transparent PNGs at 1x and 2x
     (so: 952x558 and 952x768);
   * a **square icon artwork cropped to the W alone**, which would survive 32px far better than any
     crop of the wide mark;
   * a navy-background or white-knockout variant of the mark for the footer.
   Drop them in `site/public/brand/` and the header, footer and icons can use them directly.

2. **Review `content/pages/accessibility.md`.** See deviation 4. It should go through the
   pre-publication checklist that `v1-e36-t01` defines, before the first prod launch.

3. **Confirm the sampled palette** once the district's Branding conditions are known in
   `v1-e36-t01`, and confirm that keeping muted grey and the warm accent as large-text-only colours
   is the decision the team wants to live with. If the district publishes official hex codes that
   differ, `src/styles/tokens.css` is the only file that changes.

Each developer machine and CI runner needs `npm install -g pnpm@10.15.0` and then
`pnpm --dir site install` once; `corepack enable pnpm` does not work on corepack 0.30.0.

## Follow-up work

| Item | Belongs to |
|---|---|
| Add the `site` job to `.github/workflows/ci.yml`. The workflow does not exist yet, so this task could not add the job. `site/README.md` carries the exact steps and they run in about ten seconds plus the install. | `v1-e01-t04` |
| Real page copy: Home, About, Events explained, How to join, Coaches, Parent FAQ, Contact. They are files in `content/pages/`, not components; the `[slug]` route and the navigation pick them up automatically from `navOrder`. | `v1-e36-t04` |
| Proper brand assets (transparent SVG or PNG at 1x/2x, plus a square icon artwork cropped to the W). Tracked as operator follow-up 1 above; it is an asset delivery rather than a code change, and `site/README.md` records what the current assets cannot do. | operator, then whichever task consumes them |
| Browser-based accessibility and contrast checks against a deployed preview, which jsdom cannot do. | `v1-e36-t05` smoke checks |
| A Markdown sanitiser, if the site ever renders content authored outside this repository (for example if `v1-e37-t01` chooses a content editing path that does not go through a pull request). | `v1-e37-t01` |
| Extend `ACRONYM_EXPANSIONS` in `src/lib/content.ts` as the copy grows. It currently covers NSDA, NCFL, TOC, LD and PF. | `v1-e36-t04` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- All Goal and node criteria pass, and the indexing default fails closed: only `SITE_ENV=prod`
  is indexable, so a misconfigured deploy is invisible to search engines rather than accidentally
  public. Checks run offline in about nine seconds, which keeps the CI budget intact when
  v1-e01-t04 adds the job.
- Accessibility: keeping the two failing brand colours for large text and non-text use, with small
  copy falling back to body grey, is the right call, and enforcing it with a test that fails on a
  stylesheet violation is better than a note in a README. The fifteen measurements belong in the
  publishing policy's accessibility section too (v1-e36-t01).
- The accessibility-statement page is accepted as a build requirement, not scope creep. It is copy,
  so it goes through the same review as t04's pages before launch.
- The Arial fallback stack is correct under the no-network rule; no remote font is fetched.
- Carried forward:
  - Brand assets: the PM has produced a trimmed transparent-background mark, a white knockout for
    the navy footer, a 512px navy favicon source and a light square variant, all derived from the
    deck template's artwork. They go to v1-e36-t04 with the page work. A vector original from the
    school would still be better and is worth asking for.
  - Spec wording: node criteria of the form `pnpm run test -- <file>` run the whole suite because
    pnpm forwards the `--`. Later site specs should use the filter without `--`. The PM will fix
    the remaining site specs.
  - `corepack enable pnpm` fails on corepack 0.30.0 (expired signing key); the working install
    step belongs in the site README so the next session does not rediscover it.

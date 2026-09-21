# site

The public Whitefish Bay debate team website: a Next.js App Router project that builds to plain
static files for the S3 + CloudFront distribution defined in `v1-e36-t02`.

It is deliberately separate from `web/`, the authenticated V2 app. The two share no `package.json`
and no code; they will share a domain later, not a build.

Specs: [`plan_specs/v1/e36-team-website/`](../plan_specs/v1/e36-team-website/). This directory was
created by `v1-e36-t03-site-scaffold`.

## Commands

Install once per clone, then everything below runs offline:

```bash
pnpm --dir site install
```

| Command | What it does |
|---|---|
| `pnpm --dir site dev` | Local dev server on <http://localhost:3000> |
| `pnpm --dir site lint` | ESLint: the Next rules plus the full `jsx-a11y` recommended set |
| `pnpm --dir site typecheck` | `tsc --noEmit` against a strict config |
| `pnpm --dir site test` | vitest with jsdom: content, tokens, layout, SEO, routes, contact, the login flag, the content guard, page accessibility and the offline guards |
| `pnpm --dir site build` | Static export into `site/out/` |
| `pnpm --dir site qa` | Pre-launch visual QA in a real browser. **Operator only, needs the network**: see [Pre-launch visual QA](#pre-launch-visual-qa) |

`site/scripts/pre-commit-checks.sh` runs the first four. The `site-checks` pre-commit hook runs it
whenever anything under `site/` changes; together they take about ten seconds.

Node 22.13 or newer and pnpm 10.15 are required. Install pnpm with
`npm install -g pnpm@10.15.0`: corepack 0.30.0 cannot fetch it, because the npm signing key it
was built with has expired.

## Settings

Both are read at build time only and never reach the browser.

| Variable | Values | Effect |
|---|---|---|
| `SITE_ENV` | `prod`, anything else | `prod` allows indexing and writes a sitemap reference into `robots.txt`. Every other value, including unset, is treated as `dev`: `robots.txt` disallows all paths and every page carries `noindex, nofollow`. The default fails closed on purpose, so a misconfigured build cannot put a preview into search results. |
| `SITE_URL` | an origin | Canonical URLs, Open Graph URLs and sitemap entries. Defaults to `http://localhost:3000`. |
| `SITE_DEBATER_LOGIN` | `on`, anything else | `on` puts the Debater login link in the main navigation. Anything else, including unset, leaves it out of the export entirely: not hidden, absent. It stays off until the V2 app in `web/` exists. |
| `SITE_DEBATER_LOGIN_URL` | a path or URL | Where that link points. Defaults to `/app/`, because the V2 app mounts under this same domain. |

```bash
SITE_ENV=prod SITE_URL=https://the-team-domain pnpm --dir site build
```

## Where the copy lives

No page component contains copy. Everything a visitor reads is a file under `site/content/`:

```
content/
  site.yaml            site-wide strings, the email allowlist and the Debater login label
  media-consent.yaml   who may be named, which images may be published, and when each was checked
  pages/<slug>.md      one page each; home.md renders at /, every other file at /<slug>/
  not-found.md         the 404 page, kept out of pages/ so it never enters the navigation or sitemap
```

The core pages parents need are `home`, `about`, `events`, `join`, `coaches`, `faq` and
`contact`, in that navigation order, plus the `accessibility` statement. Adding a page means
adding a file: `src/app/[slug]/page.tsx` generates a route for every one of them, so there is no
per-page component to write and no navigation list to keep in step.

Each page carries YAML front matter:

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | `<h1>`, `<title>` and the Open Graph title |
| `description` | yes | meta description and Open Graph description |
| `navLabel` | no | navigation text; defaults to the title |
| `navOrder` | no | navigation and sitemap order; unordered pages sort last, then alphabetically |
| `openGraphImage` | no | site-relative path to a share image |
| `draft` | no | `true` keeps the page out of the build entirely |

`src/lib/content.ts` validates every file against a zod schema at build time and throws with the
file name, so a page missing a title fails `pnpm --dir site build` instead of shipping.

### House style, enforced by the build

1. **No em dashes in body copy.** Use a comma, a colon or two sentences. The error names the line.
2. **Spell out every acronym.** A page that uses `NSDA`, `NCFL`, `WDCA`, `TOC`, `LD` or `PF` must
   also contain the full name somewhere on the same page. The list is `ACRONYM_EXPANSIONS` in
   `src/lib/content.ts`; add to it as the site grows. Parents and new students are the audience.
3. **Facts nobody has supplied are marked, not invented.** In prose, write `[[TBD]]` or
   `[[TBD: what is needed]]` where a fact has to come from Charlie. In a structured announcement
   such as the October 1 panel in `content/home.yaml`, give the fact an `unsetNote` instead of a
   `value`. Both render as a visible gap badge, so a dev preview shows every hole, and both fail a
   prod build until they are filled. "To be announced" is a `value`: deciding not to say is an
   answer, and only an unanswered fact is a gap.
4. **No graduation-rate, dropout or "at risk" research.** Any of that wording anywhere in
   `content/`, comments included, fails the build naming the file and the line
   (`EXCLUDED_EVIDENCE_PATTERNS` in `src/lib/content.ts`). The team brand guide rules this
   category out by name: in this district those findings answer a question nobody is asking, and
   quoting them reads as condescending. Test scores, grade point average, college readiness and
   skill acquisition are the categories that are in.
5. **Every research claim carries its source.** A claim in the academic-case band of
   `content/home.yaml` needs a `source` with the authors, the publication, the year and what was
   measured, all shown on the page; an external link is optional and must be `https://`. A claim
   whose source has not been supplied yet is written `source: '[[TBD: source]]'`, which shows as
   a TBD badge in a dev preview and fails a prod build naming the claim. Claims come only from the
   approved list in [`docs/data/academic-case-sources.md`](../docs/data/academic-case-sources.md).
6. **Home entry-point cards carry the title of the page they open.** A card whose `href` is not a
   page in `content/pages/`, or whose `title` differs from that page's title, fails the build.

## The content guard

`src/lib/publishing-policy.ts` is the part of
[`docs/policies/website-publishing.md`](../docs/policies/website-publishing.md) that a build can
check by itself. It runs over `content/` during `next build`, from `src/app/layout.tsx`, and
again over the exported HTML in `tests/content-policy.test.ts`. **A prod build fails on an error;
a dev build prints it and carries on**, so the copy can be reviewed with the gaps visible.

| It fails the build on | Because |
|---|---|
| An email address that is not in `contactEmails` in `site.yaml` | Only coach and team addresses publish; a student address never does |
| Anything shaped like a phone number | The site publishes none, of anyone |
| An image with no entry in `media-consent.yaml` | Every image of a person needs a current-season consent reference; every other image needs a line saying nobody is in it |
| A run of capitalised words that `permittedNamePhrases` cannot cover end to end | A student name cannot reach prod unreviewed. Phrases, not words: reviewing "Blue Valley West High School" must not leave Blue, Valley and West permitted on their own. The full published-names allowlist is `v1-e37-t03` |
| A named student whose consent entry is from a previous season | The district's form renews annually; consent does not carry over |
| A `[[TBD]]` marker | A half-written page is not published |
| An announcement field with an `unsetNote` rather than a value | An announcement states every fact it lists. A room of "To be announced" is a decision; an empty one is an oversight, and a panel with nothing where the room goes leaves no trace in the copy for the other rules to catch |
| A script or an iframe from another origin, in the built HTML | The site loads nothing from anyone else |

It **warns**, in every environment, when a consent entry was last checked before the current
season began. That is the start-of-season check in the policy: the warning makes a lapsed one
visible without anyone having to remember to look.

## Design tokens

`src/styles/tokens.css` is the only place a colour, type size or spacing step is defined. Its
header records where the palette came from and the measured contrast of every text-on-background
pair; `tests/tokens.test.ts` recomputes those numbers from the file so they cannot drift.

The palette was sampled by the operator from the team deck template, off the Blue Dukes "W BAY"
wordmark. The district publishes no official hex codes, so this is the team's working brand
reference until the Branding section of `docs/policies/website-publishing.md` (`v1-e36-t01`)
records something more authoritative.

Two brand colours do not reach the 4.5:1 that WCAG 2.1 AA asks of normal text:

| Colour | On white | On the panel tint |
|---|---|---|
| Muted grey `#74798E` | 4.31:1 | 3.74:1 |
| Warm accent `#B36B00` | 4.18:1 | 3.63:1 |

Rather than adjust the brand, both are restricted to large text (24px, or 18.66px bold) and to
non-text use such as borders and rules, which need only 3:1. Small secondary copy uses body grey
`#55596B` instead. A unit test fails if any stylesheet paints small text with either colour.

**Typeface.** The decks use Arial. The site may not download a font, so it asks for Arial and
falls back to metric-compatible faces already on each platform: Helvetica Neue on macOS,
Liberation Sans on Linux, Roboto on Android. That substitution is the only difference from the
deck template.

## Brand assets

| File | Size | Used for |
|---|---|---|
| `public/brand/wfb-mark-navy-transparent.png` | 441x264 | Header, linking home |
| `public/brand/wfb-mark-white-knockout.png` | 441x264 | Footer, on brand navy |
| `public/brand/wfb-mark-square-light-512.png` | 512x512 | Square light-background mark, for sharing |
| `src/app/icon.png` | 512x512 | Browser icon |
| `src/app/apple-icon.png` | 180x180 | Touch icon |
| `public/favicon.ico` | 16 to 256 | `/favicon.ico` |

**All of these are transparent PNGs**, supplied by the operator in `v1-e36-t04`. They replace the
opaque JPEG-recovered assets the scaffold shipped with, and they lift the two restrictions those
carried: the mark may now sit on any surface, and the footer uses the white knockout version on
brand navy instead of standing in a text wordmark for it. The icons are cropped square rather
than letterboxed, so the W silhouette survives 32px.

The footer mark is decorative (`alt=""`): it repeats the header's link home and carries no
information of its own, and the team name is spelled out in the wordmark beside it.

This resolves open question 6 in
[`docs/policies/website-publishing.md`](../docs/policies/website-publishing.md), which recorded
the old asset set as inadequate. An SVG set would still be better than PNGs at every size.

## Accessibility

The site targets WCAG 2.1 AA. The scaffold provides a skip link, `banner`/`main`/`contentinfo`
landmarks, one visible focus style, 44px touch targets and a navigation menu that opens with
Enter or Space and closes with Escape, returning focus to its button.

`tests/layout.test.tsx` runs axe-core over the real frame and components on the WCAG 2.1 A and AA
rule sets. `tests/pages-a11y.test.tsx` runs it over **every page**, twice: once rendered through
the frame, which always runs, and once over the exported HTML in `site/out/` when a build has
produced it. The second pass is the one the acceptance criterion is about, because it includes
the head, the `lang` attribute and Next's own markup, so `html-has-lang` and `document-title` are
evaluated as a browser would evaluate them.

axe cannot evaluate colour contrast under jsdom, which has no layout engine, so contrast is
asserted against the tokens instead, in `tests/tokens.test.ts`.

**`pnpm test` before `pnpm build` means no export yet**, which is the order CI uses, so the
suites that read `site/out/` skip themselves when it is absent rather than failing.

**A stale export is the dangerous case.** An export left over from an earlier commit is not
absent, so those suites do not skip: they check the old HTML instead of the code in front of you,
and they can pass. `site/scripts/pre-commit-checks.sh` runs test then build, so every run of it
after the first reads the export the previous run left, which is only the right one if nothing has
changed since. Build first, from the same source, whenever the export-reading suites are meant to
count:

```bash
pnpm --dir site build && pnpm --dir site test
```

## Pre-launch visual QA

`site/scripts/visual-qa.mjs` is the check the unit suite cannot do. vitest runs under jsdom, which
has no layout engine: it can tell you the October 1 panel is in the document, but not that it fits
a 390px phone, that a card grid reflows, or whether a colour pair passes, which is why the axe
colour-contrast rule is off in the unit suite. This script serves `site/out` over http and, in
headless Chromium:

* walks **every URL in `sitemap.xml`**, so a page cannot be skipped by being forgotten;
* screenshots each page at **390, 768 and 1280px**, and fails any page that scrolls sideways;
* runs **axe-core** in the page at each width on the `wcag2a`, `wcag2aa`, `wcag21a` and `wcag21aa`
  rule sets **with colour-contrast enabled**;
* runs **Lighthouse** for performance, accessibility, best practices and SEO;
* writes a Markdown score table to paste into the session report, and exits non-zero if any page
  is below the floor, axe finds anything, or a page overflows.

**It is an operator command and is not part of lint, test or build.** The browser and the scorer
are several hundred megabytes over the network, and the site job has to stay inside the CI budget
in [`docs/process/working-agreements.md`](../docs/process/working-agreements.md), so they are a
package of their own rather than devDependencies here. `tests/offline.test.ts` fails if either
turns up in `site/package.json` or in one of the four offline scripts.

**One-time operator setup**, per clone:

```bash
pnpm --dir site/scripts/visual-qa-tools install
pnpm --dir site/scripts/visual-qa-tools exec playwright install chromium
```

Then, after any change to the site:

```bash
pnpm --dir site build
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
```

| Option | Default | Meaning |
|---|---|---|
| `--min-accessibility` | 95 | Floor for the Lighthouse accessibility score on every page |
| `--min-best-practices` | 95 | Floor for the Lighthouse best-practices score on every page |
| `--out-dir` | `site/qa-artifacts` | Where the screenshots and `visual-qa-report.md` are written |

The output directory is gitignored and nothing in it is ever committed: once consent entries exist
the site will carry photographs, and an image of a student must not reach the repository
(`docs/policies/website-publishing.md`, Students 10-11). The screenshots are regenerated by
running the command again. The report records the Chromium, Lighthouse and axe-core versions that
produced the numbers, because a score with no toolchain beside it cannot be reproduced.

## What this project must not do

Enforced by `tests/offline.test.ts` and by the constraints in the task spec:

* no import from `web/`, and no shared `package.json`;
* no Next feature a static export cannot serve: no API routes, middleware, server actions or ISR;
* no third-party script, tracker, analytics tag, social embed, remote font or CDN asset;
* no network access during lint, test or build. Next telemetry is disabled in the package scripts,
  and the test suite throws on any call to `fetch`.

## Continuous integration

There is no `.github/workflows/ci.yml` in the repository yet. The `site` job belongs to
`v1-e01-t04`, which creates that workflow. It should run, on changes to `site/`:

```yaml
- run: pnpm --dir site install --frozen-lockfile
- run: pnpm --dir site lint
- run: pnpm --dir site typecheck
- run: pnpm --dir site test
- run: SITE_ENV=dev pnpm --dir site build
```

That is about ten seconds of work plus the install, well inside the CI budget in
[`docs/process/working-agreements.md`](../docs/process/working-agreements.md).

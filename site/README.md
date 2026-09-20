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
| `pnpm --dir site test` | vitest with jsdom: content, tokens, layout, SEO, offline guards |
| `pnpm --dir site build` | Static export into `site/out/` |

`site/scripts/pre-commit-checks.sh` runs all four. The `site-checks` pre-commit hook runs it
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

```bash
SITE_ENV=prod SITE_URL=https://the-team-domain pnpm --dir site build
```

## Where the copy lives

No page component contains copy. Everything a visitor reads is a file under `site/content/`:

```
content/
  site.yaml          site-wide strings: name, tagline, footer note, navigation and skip-link labels
  pages/<slug>.md    one page each; home.md renders at /, every other file at /<slug>/
  not-found.md       the 404 page, kept out of pages/ so it never enters the navigation or sitemap
```

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
2. **Spell out every acronym.** A page that uses `NSDA`, `NCFL`, `TOC`, `LD` or `PF` must also
   contain the full name somewhere on the same page. The list is `ACRONYM_EXPANSIONS` in
   `src/lib/content.ts`; add to it as the site grows. Parents and new students are the audience.

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
| `public/brand/wfb-blue-dukes-lockup.png` | 476x384 | Header, linking home |
| `public/brand/wfb-wbay-mark.png` | 455x279 | Source for the icons below |
| `src/app/icon.png` | 512x512 | Browser icon, generated from the mark |
| `src/app/apple-icon.png` | 180x180 | Touch icon, generated from the mark |
| `public/favicon.ico` | 16 to 256 | `/favicon.ico`, generated from the mark |

**Both PNGs are opaque, with a white background**, because they were recovered from a JPEG. Two
consequences the site works around:

* They may only be placed on white or very light surfaces. On anything darker a white box shows.
* The footer sits on brand navy, so it uses the `WFB Debate` wordmark as text rather than the
  mark. Do not put the mark there until a transparent version exists.

The icons letterbox the mark onto a white square. At 32px the W silhouette reads clearly, but the
"BAY" lettering inside it blurs into a smudge.

A proper asset set would be: the lockup and the mark as **SVG**, or as **transparent PNGs at 1x
and 2x**; plus a **square icon artwork** cropped to the W alone, which would survive 32px far
better than a letterboxed wide mark. See the follow-up work in
[`docs/session-reports/v1-e36-t03-site-scaffold.md`](../docs/session-reports/v1-e36-t03-site-scaffold.md).

## Accessibility

The site targets WCAG 2.1 AA. The scaffold provides a skip link, `banner`/`main`/`contentinfo`
landmarks, one visible focus style, 44px touch targets and a navigation menu that opens with
Enter or Space and closes with Escape, returning focus to its button.

`tests/layout.test.tsx` runs axe-core over the real frame and components on the WCAG 2.1 A and AA
rule sets. axe cannot evaluate colour contrast under jsdom, which has no layout engine, so
contrast is asserted against the tokens instead, in `tests/tokens.test.ts`.

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

/**
 * Pre-launch visual QA for the public team site (v1-e36-t08).
 *
 * The vitest suite runs under jsdom, which has no layout engine. It can tell you that the October
 * 1 panel is in the document; it cannot tell you that the panel fits a 390px phone, that the hero
 * is legible, that a card grid reflows, or whether a colour pair passes, which is why
 * v1-e36-t03 had to disable axe's colour-contrast rule there. This script closes that gap by
 * doing the same work in a real browser:
 *
 *   - serves the static export in site/out over http, exactly as CloudFront will serve it;
 *   - walks every URL in sitemap.xml, so a page cannot be skipped by being forgotten;
 *   - screenshots each page at 390, 768 and 1280px into a gitignored directory;
 *   - runs axe-core in the page at each width on the WCAG 2.1 A and AA rule sets, with
 *     colour-contrast enabled;
 *   - runs Lighthouse for performance, accessibility, best practices and SEO;
 *   - writes a Markdown score table for the session report, and exits non-zero if any page is
 *     below the floor or axe finds anything.
 *
 * IT IS AN OPERATOR COMMAND, NOT PART OF THE BUILD.
 * -------------------------------------------------
 * It needs a headless browser and a scoring tool, which are a download of several hundred
 * megabytes and a network connection. `pnpm --dir site lint|test|build` must stay offline and
 * finish in seconds (docs/process/working-agreements.md §1), so neither dependency is in
 * site/package.json. They live in their own package, site/scripts/visual-qa-tools/, installed
 * once by the operator; this script resolves them from there and says exactly what to run when
 * they are missing. See "Pre-launch visual QA" in site/README.md.
 *
 * Usage:
 *
 *     pnpm --dir site build
 *     pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
 *
 * The screenshots are review artifacts and are never committed: the site will carry photographs
 * of students once consent entries exist, and an image of a student must not reach the repository
 * (docs/policies/website-publishing.md, Students 10-11).
 */

import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createServer as createSocketServer } from 'node:net'
import { extname, join, resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import process from 'node:process'

const SITE_DIRECTORY = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const EXPORT_DIRECTORY = join(SITE_DIRECTORY, 'out')
const TOOLS_DIRECTORY = join(SITE_DIRECTORY, 'scripts', 'visual-qa-tools')

/**
 * The three widths, and what each one is for. 390px is an iPhone 15; 768px is a tablet in
 * portrait and the width at which the navigation menu gives way to a row of links; 1280px is the
 * laptop most parents will open it on.
 */
export const WIDTHS = [
  { width: 390, height: 844, label: 'phone' },
  { width: 768, height: 1024, label: 'tablet' },
  { width: 1280, height: 900, label: 'desktop' },
]

/** WCAG 2.1 level A and AA, which is what docs/policies/website-publishing.md commits to. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

const LIGHTHOUSE_CATEGORIES = ['performance', 'accessibility', 'best-practices', 'seo']

const CONTENT_TYPES = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.xml', 'application/xml; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.ico', 'image/x-icon'],
  ['.webp', 'image/webp'],
  ['.woff2', 'font/woff2'],
])

export class VisualQaError extends Error {}

/* ---------------------------------------------------------------------------------------------
 * Arguments
 * ------------------------------------------------------------------------------------------- */

export function parseArguments(argv) {
  const options = {
    minAccessibility: 95,
    minBestPractices: 95,
    outputDirectory: join(SITE_DIRECTORY, 'qa-artifacts'),
    widths: WIDTHS,
  }
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index]
    const value = argv[index + 1]
    switch (flag) {
      case '--min-accessibility':
        options.minAccessibility = requireScore(flag, value)
        index += 1
        break
      case '--min-best-practices':
        options.minBestPractices = requireScore(flag, value)
        index += 1
        break
      case '--out-dir':
        if (!value) throw new VisualQaError(`${flag} needs a directory`)
        options.outputDirectory = resolve(process.cwd(), value)
        index += 1
        break
      // pnpm passes the separator through to the script, so `pnpm --dir site qa -- --flag`
      // arrives here with a bare `--` in front of the flags.
      case '--':
        break
      case '--help':
      case '-h':
        options.help = true
        break
      default:
        throw new VisualQaError(`unknown option ${flag}. Run with --help.`)
    }
  }
  return options
}

function requireScore(flag, value) {
  const score = Number(value)
  if (!Number.isFinite(score) || score < 0 || score > 100) {
    throw new VisualQaError(`${flag} needs a score between 0 and 100, got ${value ?? '(nothing)'}`)
  }
  return score
}

const HELP = `visual-qa.mjs: pre-launch visual QA against the built export in site/out.

  --min-accessibility <0-100>   floor for the Lighthouse accessibility score (default 95)
  --min-best-practices <0-100>  floor for the Lighthouse best-practices score (default 95)
  --out-dir <path>              where screenshots and the report go (default site/qa-artifacts)

Build first: pnpm --dir site build. The browser and the scorer are a one-time operator install;
see "Pre-launch visual QA" in site/README.md.`

/* ---------------------------------------------------------------------------------------------
 * The QA toolchain, resolved from its own package rather than from site/node_modules
 * ------------------------------------------------------------------------------------------- */

const SETUP_INSTRUCTIONS = `The browser and the scorer are not installed. They are a one-time
operator step, deliberately kept out of site/package.json so that lint, test and build stay
offline and fast:

    pnpm --dir site/scripts/visual-qa-tools install
    pnpm --dir site/scripts/visual-qa-tools exec playwright install chromium

That downloads a few hundred megabytes and needs a network connection. Then run this again.`

async function loadQaToolchain() {
  if (!existsSync(join(TOOLS_DIRECTORY, 'node_modules'))) {
    throw new VisualQaError(SETUP_INSTRUCTIONS)
  }
  const requireFromTools = createRequire(join(TOOLS_DIRECTORY, 'package.json'))
  const load = async (name) => {
    let entry
    try {
      entry = requireFromTools.resolve(name)
    } catch {
      throw new VisualQaError(`${name} is not installed.\n\n${SETUP_INSTRUCTIONS}`)
    }
    return import(pathToFileURL(entry).href)
  }
  const version = (name) => {
    try {
      return requireFromTools(`${name}/package.json`).version
    } catch {
      return 'unknown'
    }
  }
  const { chromium } = await load('playwright')
  const lighthouseModule = await load('lighthouse')
  return {
    chromium,
    lighthouse: lighthouseModule.default ?? lighthouseModule,
    versions: {
      playwright: version('playwright'),
      lighthouse: version('lighthouse'),
      axe: createRequire(join(SITE_DIRECTORY, 'package.json'))('axe-core/package.json').version,
    },
  }
}

/* ---------------------------------------------------------------------------------------------
 * The static server: site/out as CloudFront will serve it
 * ------------------------------------------------------------------------------------------- */

/**
 * next.config.ts sets `trailingSlash: true`, so every page is a directory with an index.html in
 * it. That is also how the S3 origin is configured, so resolving the same way here is what makes
 * these results mean anything about the deployed site.
 */
export function filePathFor(urlPath) {
  const withoutQuery = urlPath.split(/[?#]/)[0]
  const relative = decodeURIComponent(withoutQuery).replace(/^\/+/, '')
  const candidate = join(EXPORT_DIRECTORY, relative)
  if (!candidate.startsWith(EXPORT_DIRECTORY)) {
    return null
  }
  if (withoutQuery.endsWith('/') || relative === '') {
    return join(candidate, 'index.html')
  }
  if (extname(candidate) === '' && existsSync(join(candidate, 'index.html'))) {
    return join(candidate, 'index.html')
  }
  return candidate
}

export async function startStaticServer() {
  const port = await freePort()
  const server = createServer((request, response) => {
    const path = filePathFor(request.url ?? '/')
    const send = async (status, file) => {
      try {
        const body = await readFile(file)
        response.writeHead(status, {
          'content-type': CONTENT_TYPES.get(extname(file)) ?? 'application/octet-stream',
          // The headers CloudFront adds are checked against the deployed site by
          // scripts/site_smoke.py; the only one that changes what a browser does with these
          // pages is the content type, so that is the only one worth reproducing here.
          'cache-control': 'no-store',
        })
        response.end(body)
      } catch {
        response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
        response.end('not found')
      }
    }
    if (path === null) {
      response.writeHead(403)
      response.end('forbidden')
      return
    }
    void (existsSync(path)
      ? send(200, path)
      : send(404, join(EXPORT_DIRECTORY, '404.html')))
  })
  await new Promise((done) => server.listen(port, '127.0.0.1', done))
  return { server, origin: `http://127.0.0.1:${port}` }
}

function freePort() {
  return new Promise((done, fail) => {
    const probe = createSocketServer()
    probe.on('error', fail)
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address()
      probe.close(() => done(port))
    })
  })
}

/* ---------------------------------------------------------------------------------------------
 * The pages under test: every <loc> in the built sitemap
 * ------------------------------------------------------------------------------------------- */

/**
 * Paths rather than whole URLs. The sitemap carries whatever origin the build was given
 * (http://localhost:3000 for a local build), and the pages are served from this script's own
 * server, so only the path is portable. Reading the sitemap rather than a list written here is
 * what makes "every page" true after someone adds a page.
 */
export async function pagePaths() {
  const sitemap = join(EXPORT_DIRECTORY, 'sitemap.xml')
  if (!existsSync(sitemap)) {
    throw new VisualQaError(
      `no built export in ${EXPORT_DIRECTORY}. Run: pnpm --dir site build`,
    )
  }
  const xml = await readFile(sitemap, 'utf8')
  const paths = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => {
    const location = match[1].trim()
    return new URL(location).pathname
  })
  if (paths.length === 0) {
    throw new VisualQaError('sitemap.xml lists no pages')
  }
  return [...new Set(paths)]
}

/* ---------------------------------------------------------------------------------------------
 * The checks
 * ------------------------------------------------------------------------------------------- */

async function runAxe(page, axeSource) {
  await page.addScriptTag({ content: axeSource })
  return page.evaluate(
    ([tags]) =>
      window.axe.run(document, {
        runOnly: { type: 'tag', values: tags },
        // The rule jsdom cannot evaluate, and therefore the whole reason this file exists.
        rules: { 'color-contrast': { enabled: true } },
        resultTypes: ['violations'],
      }),
    [AXE_TAGS],
  )
}

/** True when the page is wider than the viewport, which is the overflow a phone shows as a sideways scroll. */
function measureOverflow(page) {
  return page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }))
}

async function auditPage({ browser, origin, path, axeSource, screenshotDirectory }) {
  const context = await browser.newContext()
  const results = { path, widths: [], axeViolations: [] }
  try {
    for (const viewport of WIDTHS) {
      const page = await context.newPage()
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`${origin}${path}`, { waitUntil: 'load' })
      const name = `${path === '/' ? 'home' : path.replace(/^\/|\/$/g, '').replace(/\//g, '-')}-${viewport.width}.png`
      await page.screenshot({ path: join(screenshotDirectory, name), fullPage: true })
      const overflow = await measureOverflow(page)
      const axe = await runAxe(page, axeSource)
      results.widths.push({
        ...viewport,
        screenshot: name,
        overflows: overflow.documentWidth > overflow.viewportWidth + 1,
        documentWidth: overflow.documentWidth,
        violations: axe.violations.length,
      })
      for (const violation of axe.violations) {
        results.axeViolations.push({
          width: viewport.width,
          id: violation.id,
          impact: violation.impact,
          help: violation.help,
          nodes: violation.nodes.length,
          target: violation.nodes[0]?.target?.join(' ') ?? '',
        })
      }
      await page.close()
    }
  } finally {
    await context.close()
  }
  return results
}

async function scorePage({ lighthouse, port, url }) {
  const run = await lighthouse(url, {
    port,
    output: 'json',
    logLevel: 'error',
    onlyCategories: LIGHTHOUSE_CATEGORIES,
  })
  if (!run?.lhr) {
    throw new VisualQaError(`Lighthouse returned no result for ${url}`)
  }
  const scores = {}
  for (const category of LIGHTHOUSE_CATEGORIES) {
    const raw = run.lhr.categories[category]?.score
    // A category Lighthouse could not compute is recorded as null and reported as "not measured"
    // rather than as a number nobody produced.
    scores[category] = typeof raw === 'number' ? Math.round(raw * 100) : null
  }
  return { scores, formFactor: run.lhr.configSettings?.formFactor ?? 'mobile' }
}

/* ---------------------------------------------------------------------------------------------
 * The report
 * ------------------------------------------------------------------------------------------- */

function formatScore(score) {
  return score === null ? 'not measured' : String(score)
}

export function buildReport({ pages, versions, options, startedAt }) {
  const lines = []
  lines.push('## Lighthouse scores')
  lines.push('')
  lines.push(
    `Run ${startedAt} against a local static export, Chromium ` +
      `(playwright ${versions.playwright}), Lighthouse ${versions.lighthouse}, ` +
      `form factor ${pages[0]?.formFactor ?? 'mobile'}. Floor: accessibility ` +
      `${options.minAccessibility}, best practices ${options.minBestPractices}.`,
  )
  lines.push('')
  lines.push('| Page | Performance | Accessibility | Best practices | SEO |')
  lines.push('|---|---|---|---|---|')
  for (const page of pages) {
    lines.push(
      `| \`${page.path}\` | ${formatScore(page.scores.performance)} | ` +
        `${formatScore(page.scores.accessibility)} | ` +
        `${formatScore(page.scores['best-practices'])} | ${formatScore(page.scores.seo)} |`,
    )
  }
  lines.push('')
  lines.push('## axe-core')
  lines.push('')
  lines.push(
    `axe-core ${versions.axe} in Chromium, rule sets ${AXE_TAGS.join(', ')}, with the ` +
      'colour-contrast rule enabled. Every page was checked at each of the three widths.',
  )
  lines.push('')
  const allViolations = pages.flatMap((page) =>
    page.axeViolations.map((violation) => ({ path: page.path, ...violation })),
  )
  if (allViolations.length === 0) {
    lines.push('No violations on any page, at any width.')
  } else {
    lines.push('| Page | Width | Rule | Impact | Nodes | First node |')
    lines.push('|---|---|---|---|---|---|')
    for (const violation of allViolations) {
      lines.push(
        `| \`${violation.path}\` | ${violation.width} | ${violation.id} | ${violation.impact} | ` +
          `${violation.nodes} | \`${violation.target}\` |`,
      )
    }
  }
  lines.push('')
  lines.push('## Widths')
  lines.push('')
  lines.push('| Page | 390 | 768 | 1280 |')
  lines.push('|---|---|---|---|')
  for (const page of pages) {
    const cells = WIDTHS.map((viewport) => {
      const measured = page.widths.find((entry) => entry.width === viewport.width)
      if (!measured) return 'not measured'
      return measured.overflows
        ? `overflows (${measured.documentWidth}px wide)`
        : 'no horizontal overflow'
    })
    lines.push(`| \`${page.path}\` | ${cells.join(' | ')} |`)
  }
  lines.push('')
  lines.push(
    'Screenshots for each cell are in the output directory, named `<page>-<width>.png`. They are ' +
      'review artifacts and are never committed.',
  )
  lines.push('')
  return lines.join('\n')
}

export function findFailures(pages, options) {
  const failures = []
  for (const page of pages) {
    const accessibility = page.scores.accessibility
    const bestPractices = page.scores['best-practices']
    if (accessibility === null || accessibility < options.minAccessibility) {
      failures.push(
        `${page.path}: accessibility ${formatScore(accessibility)}, floor ${options.minAccessibility}`,
      )
    }
    if (bestPractices === null || bestPractices < options.minBestPractices) {
      failures.push(
        `${page.path}: best practices ${formatScore(bestPractices)}, floor ${options.minBestPractices}`,
      )
    }
    for (const violation of page.axeViolations) {
      failures.push(
        `${page.path} at ${violation.width}px: axe ${violation.id} (${violation.impact}), ` +
          `${violation.nodes} node(s)`,
      )
    }
    for (const width of page.widths) {
      if (width.overflows) {
        failures.push(
          `${page.path} at ${width.width}px: the page is ${width.documentWidth}px wide and scrolls sideways`,
        )
      }
    }
  }
  return failures
}

/* ---------------------------------------------------------------------------------------------
 * Main
 * ------------------------------------------------------------------------------------------- */

async function main(argv) {
  const options = parseArguments(argv)
  if (options.help) {
    console.log(HELP)
    return 0
  }

  const paths = await pagePaths()
  const { chromium, lighthouse, versions } = await loadQaToolchain()
  const axeSource = await readFile(
    createRequire(join(SITE_DIRECTORY, 'package.json')).resolve('axe-core/axe.min.js'),
    'utf8',
  )

  const screenshotDirectory = join(options.outputDirectory, 'screenshots')
  await mkdir(screenshotDirectory, { recursive: true })

  const { server, origin } = await startStaticServer()
  const debuggingPort = await freePort()
  const browser = await chromium.launch({ args: [`--remote-debugging-port=${debuggingPort}`] })

  const startedAt = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
  const pages = []
  try {
    for (const path of paths) {
      process.stderr.write(`visual-qa: ${path}\n`)
      const audited = await auditPage({
        browser,
        origin,
        path,
        axeSource,
        screenshotDirectory,
      })
      const scored = await scorePage({ lighthouse, port: debuggingPort, url: `${origin}${path}` })
      pages.push({ ...audited, ...scored })
    }
  } finally {
    await browser.close()
    await new Promise((done) => server.close(done))
  }

  const report = buildReport({ pages, versions, options, startedAt })
  const reportPath = join(options.outputDirectory, 'visual-qa-report.md')
  await writeFile(reportPath, report, 'utf8')
  console.log(report)
  console.log(`Written to ${reportPath}`)
  console.log(`Screenshots in ${screenshotDirectory}`)

  const failures = findFailures(pages, options)
  if (failures.length > 0) {
    console.error(`\nvisual-qa: ${failures.length} problem(s):`)
    for (const failure of failures) {
      console.error(`  ${failure}`)
    }
    return 1
  }
  console.log(`\nvisual-qa: ${pages.length} pages clear the floor with axe clean at every width.`)
  return 0
}

/**
 * Run only when this file is the command, so that tests/visual-qa.test.ts can import the parts
 * that need no browser (path resolution, the sitemap walk, the report, the floor) and check them
 * in the offline suite. Everything that needs Chromium stays behind `main`, which no test calls.
 */
const invokedDirectly =
  process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (invokedDirectly) {
  try {
    process.exitCode = await main(process.argv.slice(2))
  } catch (error) {
    if (error instanceof VisualQaError) {
      console.error(`visual-qa: ${error.message}`)
      process.exitCode = 2
    } else {
      throw error
    }
  }
}

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

// The QA command is plain JavaScript, deliberately: it runs under node with no build step,
// because it is an operator command rather than part of the site. tsconfig has allowJs off, so
// there is no declaration for it and everything imported here is `any`.
// @ts-expect-error - see above
import * as visualQa from '../scripts/visual-qa.mjs'

const {
  AXE_TAGS,
  WIDTHS,
  VisualQaError,
  buildReport,
  filePathFor,
  findFailures,
  pagePaths,
  parseArguments,
} = visualQa

/**
 * The parts of the browser QA command that need no browser (v1-e36-t08).
 *
 * The command itself is an operator step: it drives headless Chromium and Lighthouse, which are
 * hundreds of megabytes over the network and have no business in the CI budget. But most of what
 * could be wrong with it has nothing to do with a browser: resolving a URL to a file the way the
 * S3 origin does, reading every page out of the sitemap rather than a list somebody typed,
 * enforcing the score floor, and reporting a page that overflows. Those are checked here, offline
 * and in milliseconds, so the operator's one expensive run is not also the first time the script
 * has been executed.
 *
 * Nothing in this file launches a browser or calls `main`.
 */

const EXPORT_DIRECTORY = join(process.cwd(), 'out')
const hasExport = existsSync(join(EXPORT_DIRECTORY, 'index.html'))

describe('the options', () => {
  it('defaults both floors to 95, which is what the task spec sets', () => {
    const options = parseArguments([])
    expect(options.minAccessibility).toBe(95)
    expect(options.minBestPractices).toBe(95)
  })

  it('accepts the flags through pnpm, which passes its separator along', () => {
    const options = parseArguments(['--', '--min-accessibility', '95', '--min-best-practices', '95'])
    expect(options.minAccessibility).toBe(95)
    expect(options.minBestPractices).toBe(95)
  })

  it('refuses a floor that is not a score, rather than silently treating it as zero', () => {
    expect(() => parseArguments(['--min-accessibility', 'high'])).toThrow(VisualQaError)
    expect(() => parseArguments(['--min-accessibility'])).toThrow(VisualQaError)
    expect(() => parseArguments(['--min-best-practices', '120'])).toThrow(VisualQaError)
  })

  it('refuses an option it does not know, rather than ignoring a misspelled floor', () => {
    expect(() => parseArguments(['--min-accessibilty', '95'])).toThrow(/unknown option/)
  })
})

describe('serving the export the way the origin serves it', () => {
  it('resolves a trailing-slash route to its index.html, as next.config.ts exports it', () => {
    expect(filePathFor('/')).toBe(join(EXPORT_DIRECTORY, 'index.html'))
    expect(filePathFor('/faq/')).toBe(join(EXPORT_DIRECTORY, 'faq', 'index.html'))
  })

  it('serves an asset by its own path', () => {
    expect(filePathFor('/_next/static/chunk.js')).toBe(
      join(EXPORT_DIRECTORY, '_next', 'static', 'chunk.js'),
    )
    expect(filePathFor('/sitemap.xml')).toBe(join(EXPORT_DIRECTORY, 'sitemap.xml'))
  })

  it('drops a query string, which a page may carry and a file never has', () => {
    expect(filePathFor('/faq/?topic=cost')).toBe(join(EXPORT_DIRECTORY, 'faq', 'index.html'))
  })

  it('refuses a path that climbs out of the export', () => {
    expect(filePathFor('/../../etc/passwd')).toBeNull()
  })
})

describe('the pages under test', () => {
  it.runIf(hasExport)('is every page in the built sitemap, and nothing typed by hand', async () => {
    const paths = await pagePaths()
    const sitemap = readFileSync(join(EXPORT_DIRECTORY, 'sitemap.xml'), 'utf8')
    const listed = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (match) => new URL(match[1] as string).pathname,
    )
    expect(paths).toEqual(listed)
    expect(paths).toContain('/')
  })
})

/*
 * There is deliberately no test here that starts the local server and fetches from it. tests/
 * setup.ts turns any call to fetch into a failure, on purpose, and a loopback request to a server
 * a test started is still a socket: weakening that guard to cover twenty lines of readFile and a
 * content-type header is a bad trade. Everything the server decides lives in filePathFor above,
 * which is tested directly. The serving itself is exercised by the operator's QA run, and the
 * v1-e36-t08 session report records that run.
 */

describe('the floor', () => {
  const page = (overrides = {}) => ({
    path: '/faq/',
    scores: { performance: 99, accessibility: 100, 'best-practices': 100, seo: 100 },
    formFactor: 'mobile',
    axeViolations: [],
    widths: WIDTHS.map((viewport: { width: number }) => ({
      ...viewport,
      overflows: false,
      documentWidth: viewport.width,
      violations: 0,
    })),
    ...overrides,
  })
  const options = { minAccessibility: 95, minBestPractices: 95 }

  it('passes a page that clears both floors with axe clean and no overflow', () => {
    expect(findFailures([page()], options)).toEqual([])
  })

  it('fails a page below the accessibility floor', () => {
    const scores = { performance: 99, accessibility: 94, 'best-practices': 100, seo: 100 }
    expect(findFailures([page({ scores })], options).join('\n')).toMatch(
      /accessibility 94, floor 95/,
    )
  })

  it('fails a page below the best-practices floor', () => {
    const scores = { performance: 99, accessibility: 100, 'best-practices': 83, seo: 100 }
    expect(findFailures([page({ scores })], options).join('\n')).toMatch(
      /best practices 83, floor 95/,
    )
  })

  /**
   * A category Lighthouse could not compute is not a pass. Treating it as one is how a run that
   * half worked gets recorded as a green launch gate.
   */
  it('fails a page whose score was never produced, rather than assuming it', () => {
    const scores = { performance: null, accessibility: null, 'best-practices': 100, seo: 100 }
    expect(findFailures([page({ scores })], options).join('\n')).toMatch(
      /accessibility not measured, floor 95/,
    )
  })

  it('fails on any axe violation, whatever the scores say', () => {
    const axeViolations = [
      { width: 390, id: 'color-contrast', impact: 'serious', help: 'Elements must have sufficient colour contrast', nodes: 2, target: '.hero__lead' },
    ]
    expect(findFailures([page({ axeViolations })], options).join('\n')).toMatch(
      /at 390px: axe color-contrast \(serious\), 2 node\(s\)/,
    )
  })

  it('fails a page that scrolls sideways at any width', () => {
    const widths = WIDTHS.map((viewport: { width: number }) => ({
      ...viewport,
      overflows: viewport.width === 390,
      documentWidth: viewport.width === 390 ? 430 : viewport.width,
      violations: 0,
    }))
    expect(findFailures([page({ widths })], options).join('\n')).toMatch(
      /at 390px: the page is 430px wide and scrolls sideways/,
    )
  })
})

describe('the report', () => {
  const pages = [
    {
      path: '/',
      scores: { performance: 98, accessibility: 100, 'best-practices': 100, seo: 100 },
      formFactor: 'mobile',
      axeViolations: [],
      widths: WIDTHS.map((viewport: { width: number }) => ({
        ...viewport,
        overflows: false,
        documentWidth: viewport.width,
        violations: 0,
      })),
    },
  ]
  const report = buildReport({
    pages,
    versions: { playwright: '1.0.0', lighthouse: '12.0.0', axe: '4.13.0' },
    options: { minAccessibility: 95, minBestPractices: 95 },
    startedAt: '2026-09-20 21:00 UTC',
  }) as string

  it('is Markdown the session report can carry as it stands', () => {
    expect(report).toContain('| Page | Performance | Accessibility | Best practices | SEO |')
    expect(report).toContain('| `/` | 98 | 100 | 100 | 100 |')
  })

  it('names the three widths the task asks about', () => {
    expect(report).toContain('| Page | 390 | 768 | 1280 |')
  })

  it('names the rule sets axe ran, so the claim can be checked', () => {
    for (const tag of AXE_TAGS) {
      expect(report).toContain(tag)
    }
    expect(report).toContain('colour-contrast rule enabled')
  })

  it('records the toolchain that produced the numbers', () => {
    expect(report).toMatch(/playwright 1\.0\.0/)
    expect(report).toMatch(/Lighthouse 12\.0\.0/)
    expect(report).toMatch(/axe-core 4\.13\.0/)
  })
})

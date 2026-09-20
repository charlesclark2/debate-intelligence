import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Prose } from '@/components/Prose'
import { SiteFrame } from '@/components/SiteFrame'
import type { ContentPage } from '@/lib/content'
import { HOME_SLUG, loadNotFoundPage, loadPages, loadSiteSettings } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * Every page on this site meets WCAG 2.1 level AA (v1-e36-t04 acceptance criterion 5, and
 * docs/policies/website-publishing.md Accessibility 1, where a violation is a build failure and
 * not a backlog item).
 *
 * Two passes, because each catches what the other cannot:
 *
 *   1. Every content page rendered through the real frame. This always runs, including in CI,
 *      where `pnpm test` comes before `pnpm build` and there is no export yet.
 *   2. The exported HTML in site/out/, when a build has produced it. That is the artefact
 *      CloudFront serves, so it is the one the criterion is really about: it includes the head,
 *      the lang attribute, Next's own markup and the icon links, none of which pass 1 sees.
 *
 * axe cannot evaluate colour contrast under jsdom, which has no layout engine. tests/axe.ts
 * disables that rule explicitly and tests/tokens.test.ts asserts the ratios against the design
 * tokens instead.
 */

const settings = loadSiteSettings()
const pages = loadPages()
const outDirectory = join(process.cwd(), 'out')
const hasExport = existsSync(join(outDirectory, 'index.html'))

const navigationItems = pages.map((page) => ({ href: page.route, label: page.navLabel }))

function exportedPath(slug: string): string {
  return slug === HOME_SLUG
    ? join(outDirectory, 'index.html')
    : join(outDirectory, slug, 'index.html')
}

/**
 * Landmark rules only hold when banner, main and contentinfo are top level, so the frame goes
 * straight into document.body rather than the wrapper testing-library adds by default.
 */
function renderPage(page: ContentPage) {
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      <h1>{page.title}</h1>
      <Prose html={page.html} />
    </SiteFrame>,
    { container: document.body },
  )
}

describe('every content page, rendered through the site frame', () => {
  it.each(pages.map((page) => [page.slug, page] as const))(
    '%s has no WCAG 2.1 AA violation',
    async (_slug, page) => {
      renderPage(page)
      const violations = await findAccessibilityViolations(document.body)
      expect(violations, describeViolations(violations)).toEqual([])
    },
  )

  it('the 404 page has no WCAG 2.1 AA violation', async () => {
    renderPage(loadNotFoundPage())
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

describe('every page has exactly one h1 and headings in order', () => {
  it.each(pages.map((page) => [page.slug, page] as const))('%s', (_slug, page) => {
    renderPage(page)
    expect(document.querySelectorAll('h1')).toHaveLength(1)

    const levels = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number.parseInt(heading.tagName.slice(1), 10),
    )
    for (const [index, level] of levels.entries()) {
      if (index > 0) {
        expect(level, `${page.filePath} jumps from h${levels[index - 1]} to h${level}`).toBeLessThanOrEqual(
          levels[index - 1]! + 1,
        )
      }
    }
  })
})

describe('every image carries alt text', () => {
  it.each(pages.map((page) => [page.slug, page] as const))('%s', (_slug, page) => {
    renderPage(page)
    for (const image of document.querySelectorAll('img')) {
      expect(image.getAttribute('alt'), `${page.filePath}: ${image.getAttribute('src')}`).not.toBeNull()
    }
  })
})

/**
 * The exported files, which is what the acceptance criterion means by "every built page". The
 * whole document is replaced, head and all, so document-level rules such as html-has-lang and
 * document-title are evaluated as a browser would evaluate them.
 */
describe.runIf(hasExport)('every built page in site/out/', () => {
  const originalLang = document.documentElement.lang

  afterEach(() => {
    document.documentElement.lang = originalLang
    document.documentElement.innerHTML = '<head></head><body></body>'
  })

  function loadBuiltPage(slug: string) {
    const html = readFileSync(exportedPath(slug), 'utf8')
    document.documentElement.lang = /<html[^>]*\blang="([^"]*)"/.exec(html)?.[1] ?? ''
    const head = /<head>([\s\S]*?)<\/head>/.exec(html)?.[1] ?? ''
    const body = /<body[^>]*>([\s\S]*?)<\/body>/.exec(html)?.[1] ?? ''
    document.documentElement.innerHTML = `<head>${head}</head><body>${body}</body>`
  }

  it.each([...pages.map((page) => page.slug), '404'])(
    '%s has no WCAG 2.1 AA violation',
    async (slug) => {
      loadBuiltPage(slug)
      const violations = await findAccessibilityViolations(document.documentElement)
      expect(violations, `${slug}:\n${describeViolations(violations)}`).toEqual([])
    },
  )

  it.each([...pages.map((page) => page.slug)])('%s declares a language and a title', (slug) => {
    loadBuiltPage(slug)
    expect(document.documentElement.lang).toBe('en')
    expect(document.title.length).toBeGreaterThan(0)
  })
})

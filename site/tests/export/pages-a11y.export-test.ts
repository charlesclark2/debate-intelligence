import { readFileSync } from 'node:fs'

import { afterEach, describe, expect, it } from 'vitest'

import { loadPages } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from '../axe'
import { exportedPagePath } from './built-export'

/**
 * Every page on this site meets WCAG 2.1 level AA, checked on the exported HTML (v1-e36-t04
 * acceptance criterion 5). This is the second of the two passes tests/pages-a11y.test.tsx
 * describes: the files CloudFront serves, head and all.
 */

const pages = loadPages()

/**
 * The exported files, which is what the acceptance criterion means by "every built page". The
 * whole document is replaced, head and all, so document-level rules such as html-has-lang and
 * document-title are evaluated as a browser would evaluate them.
 */
describe('every built page in site/out/', () => {
  const originalLang = document.documentElement.lang

  afterEach(() => {
    document.documentElement.lang = originalLang
    document.documentElement.innerHTML = '<head></head><body></body>'
  })

  function loadBuiltPage(slug: string) {
    const html = readFileSync(exportedPagePath(slug), 'utf8')
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

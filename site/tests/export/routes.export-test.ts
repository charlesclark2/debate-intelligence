import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { loadPages } from '@/lib/content'

import { exportDirectory, exportedPagePath } from './built-export'

/**
 * The core pages parents need, as the build wrote them (v1-e36-t04 acceptance criterion 1):
 * every one has a file in site/out/, its own title and description, a link from every other
 * core page, and an entry in the exported sitemap.xml. tests/routes.test.ts checks the sources.
 */

const CORE_PAGES = ['home', 'about', 'events', 'schedule', 'join', 'coaches', 'faq', 'contact'] as const

describe('the static export', () => {
  it.each(CORE_PAGES)('writes %s to site/out/', (slug) => {
    expect(existsSync(exportedPagePath(slug)), exportedPagePath(slug)).toBe(true)
  })

  it('gives every built page its own <title> and meta description', () => {
    const seen = new Map<string, string>()
    for (const slug of CORE_PAGES) {
      const html = readFileSync(exportedPagePath(slug), 'utf8')
      const title = /<title>([^<]*)<\/title>/.exec(html)?.[1]
      const description = /<meta name="description" content="([^"]*)"/.exec(html)?.[1]
      expect(title, `${slug} <title>`).toBeTruthy()
      expect(description, `${slug} meta description`).toBeTruthy()
      expect(seen.has(title!), `${slug} reuses the title of ${seen.get(title!)}`).toBe(false)
      seen.set(title!, slug)
    }
  })

  it.each(CORE_PAGES)('reaches %s from the navigation on every page', (slug) => {
    const route = loadPages().find((page) => page.slug === slug)!.route
    for (const other of CORE_PAGES) {
      const html = readFileSync(exportedPagePath(other), 'utf8')
      expect(html, `${other} does not link to ${route}`).toContain(`href="${route}"`)
    }
  })

  it('lists every core page in the exported sitemap.xml', () => {
    const xml = readFileSync(join(exportDirectory, 'sitemap.xml'), 'utf8')
    for (const slug of CORE_PAGES) {
      const route = loadPages().find((page) => page.slug === slug)!.route
      expect(xml, `sitemap.xml is missing ${route}`).toContain(`${route}</loc>`)
    }
  })
})

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import { generateStaticParams } from '@/app/[slug]/page'
import sitemap from '@/app/sitemap'
import { HOME_SLUG, loadPages, loadRoutedPages } from '@/lib/content'

/**
 * The core pages parents need before the October 1 information session (v1-e36-t04 acceptance
 * criterion 1): every one of them exists, carries its own title and description, has a route in
 * the static export, appears in the navigation, and is listed in sitemap.xml.
 *
 * The export itself is only checked when site/out/ is present, because `pnpm --dir site test`
 * runs before `pnpm --dir site build` in CI and building here would blow the CI budget in
 * docs/process/working-agreements.md. `site/scripts/pre-commit-checks.sh` runs both, in that
 * order, so a developer machine checks the real files as well.
 */

const CORE_PAGES = ['home', 'about', 'events', 'join', 'coaches', 'faq', 'contact'] as const

const outDirectory = join(process.cwd(), 'out')
const hasExport = existsSync(join(outDirectory, 'index.html'))

function exportedPath(slug: string): string {
  return slug === HOME_SLUG
    ? join(outDirectory, 'index.html')
    : join(outDirectory, slug, 'index.html')
}

describe('the core pages exist as content', () => {
  const pages = loadPages()

  it.each(CORE_PAGES)('has a %s page', (slug) => {
    expect(pages.map((page) => page.slug)).toContain(slug)
  })

  it('gives every page its own title and description', () => {
    const titles = pages.map((page) => page.title)
    const descriptions = pages.map((page) => page.description)
    expect(new Set(titles).size).toBe(titles.length)
    expect(new Set(descriptions).size).toBe(descriptions.length)
    for (const page of pages) {
      expect(page.title.length, page.filePath).toBeGreaterThan(0)
      expect(page.description.length, page.filePath).toBeGreaterThan(0)
    }
  })

  it('orders the navigation for a parent: about, events, join, coaches, then the questions', () => {
    const order = pages.map((page) => page.slug)
    expect(order.slice(0, 7)).toEqual([...CORE_PAGES])
  })

  // The navigation is a single row from --breakpoint-nav up. "Accessibility", at 13 characters,
  // is the longest label that still fits beside the lockup on a 360px phone once the menu opens.
  it('gives each page a navigation label short enough for the nav bar', () => {
    for (const page of pages) {
      expect(page.navLabel.length, `${page.filePath} navLabel`).toBeLessThanOrEqual(13)
    }
  })
})

describe('the static export', () => {
  it('generates a route for every page except home, which is the root', () => {
    const slugs = generateStaticParams().map((params) => params.slug)
    expect(slugs).toEqual(loadRoutedPages().map((page) => page.slug))
    for (const slug of CORE_PAGES) {
      if (slug !== HOME_SLUG) {
        expect(slugs, `no route for ${slug}`).toContain(slug)
      }
    }
    expect(slugs).not.toContain(HOME_SLUG)
  })

  it.each(CORE_PAGES)('lists %s in sitemap.xml', (slug) => {
    vi.stubEnv('SITE_ENV', 'prod')
    vi.stubEnv('SITE_URL', 'https://wfbdebate.example.invalid')
    const page = loadPages().find((candidate) => candidate.slug === slug)
    expect(page).toBeDefined()
    expect(sitemap().map((entry) => entry.url)).toContain(
      `https://wfbdebate.example.invalid${page!.route}`,
    )
  })

  it.runIf(hasExport).each(CORE_PAGES)('writes %s to site/out/', (slug) => {
    expect(existsSync(exportedPath(slug)), exportedPath(slug)).toBe(true)
  })

  it.runIf(hasExport)('gives every built page its own <title> and meta description', () => {
    const seen = new Map<string, string>()
    for (const slug of CORE_PAGES) {
      const html = readFileSync(exportedPath(slug), 'utf8')
      const title = /<title>([^<]*)<\/title>/.exec(html)?.[1]
      const description = /<meta name="description" content="([^"]*)"/.exec(html)?.[1]
      expect(title, `${slug} <title>`).toBeTruthy()
      expect(description, `${slug} meta description`).toBeTruthy()
      expect(seen.has(title!), `${slug} reuses the title of ${seen.get(title!)}`).toBe(false)
      seen.set(title!, slug)
    }
  })

  it.runIf(hasExport).each(CORE_PAGES)('reaches %s from the navigation on every page', (slug) => {
    const route = loadPages().find((page) => page.slug === slug)!.route
    for (const other of CORE_PAGES) {
      const html = readFileSync(exportedPath(other), 'utf8')
      expect(html, `${other} does not link to ${route}`).toContain(`href="${route}"`)
    }
  })

  it.runIf(hasExport)('lists every core page in the exported sitemap.xml', () => {
    const xml = readFileSync(join(outDirectory, 'sitemap.xml'), 'utf8')
    for (const slug of CORE_PAGES) {
      const route = loadPages().find((page) => page.slug === slug)!.route
      expect(xml, `sitemap.xml is missing ${route}`).toContain(`${route}</loc>`)
    }
  })
})

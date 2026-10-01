import { existsSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import { generateStaticParams } from '@/app/[slug]/page'
import sitemap from '@/app/sitemap'
import { COMPOSED_SLUGS, HOME_SLUG, loadPages, loadRoutedPages } from '@/lib/content'

/**
 * The core pages parents need before the October 1 information session (v1-e36-t04 acceptance
 * criterion 1): every one of them exists, carries its own title and description, has a route in
 * the static export, appears in the navigation, and is listed in sitemap.xml.
 *
 * The files the build writes are checked in tests/export/routes.export-test.ts, which runs after
 * every build: `pnpm --dir site test` reads only sources, so it stays fast straight after an edit.
 */

const CORE_PAGES = ['home', 'about', 'events', 'join', 'coaches', 'faq', 'contact'] as const

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
  it('generates a route for every Markdown page that is not composed by a module of its own', () => {
    const slugs = generateStaticParams().map((params) => params.slug)
    expect(slugs).toEqual(loadRoutedPages().map((page) => page.slug))
    for (const slug of COMPOSED_SLUGS) {
      expect(slugs, `${slug} has a route module of its own and must not also be generated here`)
        .not.toContain(slug)
    }
  })

  /**
   * A composed page (v1-e36-t07) is a route module under src/app/ rather than a run of Markdown
   * poured into a column, so it does not come from generateStaticParams above. Every core page is
   * still reachable: either the dynamic segment generates it, or its own page.tsx exists.
   */
  it.each(CORE_PAGES)('reaches %s either from the dynamic segment or its own route module', (slug) => {
    if (slug === HOME_SLUG) {
      expect(existsSync(join(process.cwd(), 'src/app/page.tsx'))).toBe(true)
      return
    }
    const generated = generateStaticParams().map((params) => params.slug)
    const ownModule = join(process.cwd(), 'src/app', slug, 'page.tsx')
    expect(
      generated.includes(slug) || existsSync(ownModule),
      `${slug} has neither a generated route nor ${ownModule}`,
    ).toBe(true)
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
})

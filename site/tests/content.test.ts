import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  ContentValidationError,
  HOME_SLUG,
  loadNotFoundPage,
  loadPages,
  loadRoutedPages,
  loadSiteSettings,
} from '@/lib/content'

const fixture = (name: string) => join(process.cwd(), 'tests/fixtures', name)
const siteContent = join(process.cwd(), 'content')

describe('loading the published pages', () => {
  it('orders pages by navOrder and leaves drafts out of the export', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.map((page) => page.slug)).toEqual(['home', 'alpha', 'zulu'])
    expect(pages.map((page) => page.slug)).not.toContain('unfinished')
  })

  it('routes the home page at the root and every other page under its slug', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.find((page) => page.slug === HOME_SLUG)?.route).toBe('/')
    expect(pages.find((page) => page.slug === 'alpha')?.route).toBe('/alpha/')
  })

  it('falls back to the title when a page sets no navLabel', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.find((page) => page.slug === 'alpha')?.navLabel).toBe('Alpha')
    expect(pages.find((page) => page.slug === 'zulu')?.navLabel).toBe('Zulu fixture')
  })

  it('renders the Markdown body to HTML at build time', () => {
    const zulu = loadPages(fixture('ordering')).find((page) => page.slug === 'zulu')
    expect(zulu?.html).toContain('<h2>A heading</h2>')
    expect(zulu?.html).toContain('<a href="/">link</a>')
  })

  it('keeps the home page out of the /<slug>/ routes', () => {
    expect(loadRoutedPages(fixture('ordering')).map((page) => page.slug)).toEqual(['alpha', 'zulu'])
  })

  it('validates the 404 copy with the same schema, outside pages/', () => {
    const notFound = loadNotFoundPage(fixture('ordering'))
    expect(notFound.title).toBe('Page not found fixture')
    expect(loadPages(fixture('ordering')).map((page) => page.slug)).not.toContain('not-found')
  })
})

describe('front matter validation', () => {
  it('fails, naming the file, when a page has no title', () => {
    expect(() => loadPages(fixture('missing-title'))).toThrowError(ContentValidationError)
    expect(() => loadPages(fixture('missing-title'))).toThrowError(
      /content\/pages\/broken\.md: invalid front matter \(.*title/,
    )
  })

  it('fails, naming the file, when a page has no description', () => {
    expect(() => loadPages(fixture('missing-description'))).toThrowError(
      /content\/pages\/broken\.md: invalid front matter \(.*description/,
    )
  })

  it('names the offending file on the error object as well as in the message', () => {
    try {
      loadPages(fixture('missing-title'))
      expect.unreachable('loadPages should have thrown')
    } catch (error) {
      expect(error).toBeInstanceOf(ContentValidationError)
      expect((error as ContentValidationError).filePath).toBe('content/pages/broken.md')
    }
  })
})

describe('house style', () => {
  it('rejects an em dash in body copy and points at the line', () => {
    expect(() => loadPages(fixture('em-dash'))).toThrowError(
      /content\/pages\/dash\.md: line 6 uses an em dash/,
    )
  })

  it('rejects an acronym that the page never spells out', () => {
    expect(() => loadPages(fixture('unexpanded-acronym'))).toThrowError(
      /content\/pages\/events\.md: uses "NSDA" without spelling it out/,
    )
  })
})

describe('the site settings file', () => {
  it('reads the strings the layout needs', () => {
    const settings = loadSiteSettings(fixture('ordering'))
    expect(settings.navigationLabel).toBe('Main')
    expect(settings.skipLinkLabel).toBe('Skip to main content')
  })

  it('fails, naming the file, when the settings file is missing', () => {
    expect(() => loadSiteSettings(fixture('em-dash'))).toThrowError(
      /content\/site\.yaml: file is missing/,
    )
  })
})

describe('the content this site actually ships', () => {
  it('passes every schema and house-style rule', () => {
    const pages = loadPages(siteContent)
    expect(pages.length).toBeGreaterThan(0)
    for (const page of pages) {
      expect(page.title.length).toBeGreaterThan(0)
      expect(page.description.length).toBeGreaterThan(0)
    }
    expect(() => loadNotFoundPage(siteContent)).not.toThrow()
    expect(() => loadSiteSettings(siteContent)).not.toThrow()
  })

  it('has a home page, which is what the root route renders', () => {
    expect(loadPages(siteContent).map((page) => page.slug)).toContain(HOME_SLUG)
  })
})

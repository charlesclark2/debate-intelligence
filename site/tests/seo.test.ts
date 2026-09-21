import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import robots from '@/app/robots'
import sitemap from '@/app/sitemap'
import { loadPages } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'
import { DEFAULT_SITE_URL, absoluteUrl, isIndexable, readSiteUrl } from '@/lib/site-settings'

const PROD_URL = 'https://debate.example.invalid'
const fixture = (name: string) => join(process.cwd(), 'tests/fixtures', name)

function setEnvironment(siteEnv: string | undefined, siteUrl: string | undefined) {
  vi.stubEnv('SITE_ENV', siteEnv)
  vi.stubEnv('SITE_URL', siteUrl)
}

describe('SITE_ENV decides whether the build may be indexed', () => {
  it('treats prod as indexable', () => {
    setEnvironment('prod', PROD_URL)
    expect(isIndexable()).toBe(true)
  })

  it.each([['dev'], [undefined], ['staging'], ['PROD'], ['']])(
    'treats %s as not indexable, so a misconfigured build fails closed',
    (value) => {
      setEnvironment(value, PROD_URL)
      expect(isIndexable()).toBe(false)
    },
  )
})

describe('SITE_URL', () => {
  it('falls back to the local dev server when it is unset', () => {
    setEnvironment('dev', undefined)
    expect(readSiteUrl()).toBe(DEFAULT_SITE_URL)
  })

  it('drops a trailing slash so routes can be appended', () => {
    setEnvironment('prod', `${PROD_URL}/`)
    expect(readSiteUrl()).toBe(PROD_URL)
    expect(absoluteUrl('/accessibility/')).toBe(`${PROD_URL}/accessibility/`)
  })
})

describe('robots.txt', () => {
  it('disallows every path in a dev build and advertises no sitemap', () => {
    setEnvironment('dev', 'https://dev.example.invalid')
    const result = robots()
    expect(result.rules).toEqual([{ userAgent: '*', disallow: '/' }])
    expect(result.sitemap).toBeUndefined()
  })

  it('allows crawling and points at the sitemap in a prod build', () => {
    setEnvironment('prod', PROD_URL)
    const result = robots()
    expect(result.rules).toEqual([{ userAgent: '*', allow: '/' }])
    expect(result.sitemap).toBe(`${PROD_URL}/sitemap.xml`)
  })
})

describe('sitemap.xml', () => {
  it('lists every published content page as an absolute URL', () => {
    setEnvironment('prod', PROD_URL)
    const routes = sitemap().map((entry) => entry.url)
    const expected = loadPages().map((page) => `${PROD_URL}${page.route}`)

    expect(routes).toEqual(expected)
    expect(routes).toContain(`${PROD_URL}/`)
    expect(routes.length).toBeGreaterThan(1)
    for (const url of routes) {
      expect(url.startsWith(`${PROD_URL}/`)).toBe(true)
    }
  })

  it('leaves out drafts and the 404 page', () => {
    setEnvironment('prod', PROD_URL)
    const routes = sitemap().map((entry) => entry.url)
    expect(routes.some((url) => url.includes('not-found'))).toBe(false)
  })

  it('records no lastModified, so the export is reproducible between checkouts', () => {
    setEnvironment('prod', PROD_URL)
    for (const entry of sitemap()) {
      expect(entry.lastModified).toBeUndefined()
    }
  })
})

describe('per-page metadata', () => {
  const page = () => loadPages(fixture('ordering')).filter((candidate) => candidate.slug === 'alpha')[0]!

  it('takes the title and description from the page front matter', () => {
    setEnvironment('prod', PROD_URL)
    const metadata = buildPageMetadata(page(), fixture('ordering'))
    expect(metadata.title).toBe('Alpha fixture')
    expect(metadata.description).toBe('Sorts before Zulu by navOrder.')
  })

  it('sets a canonical URL and Open Graph tags from SITE_URL', () => {
    setEnvironment('prod', PROD_URL)
    const metadata = buildPageMetadata(page(), fixture('ordering'))
    expect(metadata.alternates?.canonical).toBe(`${PROD_URL}/alpha/`)
    expect(metadata.openGraph?.url).toBe(`${PROD_URL}/alpha/`)
    expect(metadata.openGraph?.title).toBe('Alpha fixture')
    expect(metadata.openGraph).toMatchObject({ type: 'website', siteName: 'Fixture Site' })
  })

  it('marks a dev build noindex, nofollow on every page', () => {
    setEnvironment('dev', 'https://dev.example.invalid')
    const metadata = buildPageMetadata(page(), fixture('ordering'))
    expect(metadata.robots).toEqual({ index: false, follow: false })
  })

  it('allows indexing in a prod build', () => {
    setEnvironment('prod', PROD_URL)
    const metadata = buildPageMetadata(page(), fixture('ordering'))
    expect(metadata.robots).toEqual({ index: true, follow: true })
  })
})

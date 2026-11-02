import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { exportDirectory } from './built-export'

/**
 * The announcements as the build wrote them (v1-e37-t03). Which announcements are published
 * depends on the day the export was built, and the coach adds and expires them, so this reads no
 * entry: it checks that /news/ is there, and that the sitemap and the announcement pages in
 * site/out/news/ agree, page for page. An expired announcement is in neither; that it is in
 * neither is tests/announcements.test.tsx's, on fixtures with a fixed build date.
 */

const NEWS = join(exportDirectory, 'news')

function sitemapNewsPaths(): string[] {
  const xml = readFileSync(join(exportDirectory, 'sitemap.xml'), 'utf8')
  return [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)]
    .map((match) => new URL(match[1] as string).pathname)
    .filter((path) => path.startsWith('/news/') && path !== '/news/')
}

function exportedNewsPaths(): string[] {
  return readdirSync(NEWS, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && existsSync(join(NEWS, entry.name, 'index.html')))
    .map((entry) => `/news/${entry.name}/`)
}

describe('the news pages in the export', () => {
  it('writes /news/ and lists it in the sitemap', () => {
    expect(existsSync(join(NEWS, 'index.html'))).toBe(true)
    expect(readFileSync(join(exportDirectory, 'sitemap.xml'), 'utf8')).toContain('/news/</loc>')
  })

  it('has a page for every announcement in the sitemap, and none that it leaves out', () => {
    expect(exportedNewsPaths().sort()).toEqual(sitemapNewsPaths().sort())
  })

  it('links every announcement page from /news/', () => {
    const list = readFileSync(join(NEWS, 'index.html'), 'utf8')
    for (const path of sitemapNewsPaths()) {
      expect(list, `/news/ does not link to ${path}`).toContain(`href="${path}"`)
    }
  })
})

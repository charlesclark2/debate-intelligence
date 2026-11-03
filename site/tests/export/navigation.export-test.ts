import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { loadPages, loadSiteSettings } from '@/lib/content'

import { exportedFiles, exportedPagePath, readExported } from './built-export'

/**
 * Navigation and footer placement in the built files, which is what a visitor actually gets
 * (v1-e36-t07 acceptance criterion 0). tests/navigation.test.tsx checks the rendered components.
 */

const settings = loadSiteSettings()
const pages = loadPages()

describe('the exported navigation', () => {
  const read = (slug: string) => readFileSync(exportedPagePath(slug), 'utf8')

  const section = (html: string, tag: 'header' | 'footer') =>
    new RegExp(`<${tag}[\\s\\S]*?</${tag}>`).exec(html)?.[0] ?? ''

  it.each(settings.primaryNavigation)('%s marks itself current in the export', (slug) => {
    const route = pages.find((page) => page.slug === slug)!.route
    const header = section(read(slug), 'header')
    expect(header, `${slug} has no header in the export`).not.toBe('')
    const current = [...header.matchAll(/<a[^>]*aria-current="page"[^>]*>/g)]
    expect(current, `${slug} marks no navigation link as the current page`).toHaveLength(1)
    expect(current[0]?.[0]).toContain(`href="${route}"`)
  })

  it.each(settings.primaryNavigation)('%s keeps the utility links in the footer', (slug) => {
    const html = read(slug)
    expect(section(html, 'footer')).toContain('href="/accessibility/"')
    expect(section(html, 'header')).not.toContain('href="/accessibility/"')
  })

  // v1-e37-t15: News is in the header and stays in the footer, on every page the export writes,
  // the announcement pages and the 404 page included.
  it.each(exportedFiles().filter((path) => path.endsWith('.html')))(
    '%s links News from the header and the footer',
    (path) => {
      const html = readExported(path)
      expect(section(html, 'header'), `${path} has no News link in its header`).toContain(
        'href="/news/"',
      )
      expect(section(html, 'footer'), `${path} has no News link in its footer`).toContain(
        'href="/news/"',
      )
    },
  )

  it('marks nothing current on a page outside the navigation', () => {
    expect(section(read('accessibility'), 'header')).not.toContain('aria-current')
  })
})

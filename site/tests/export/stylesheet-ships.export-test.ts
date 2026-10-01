import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { exportDirectory as outDirectory } from './built-export'

/**
 * The exported HTML links a stylesheet and that stylesheet is in the export: the half of
 * tests/stylesheet-ships.test.ts that needs a build, and the half that would have caught the
 * unstyled export v1-e36-t04 shipped to the dev preview.
 */

const EXPORTED_PAGES = [
  'index.html',
  'about/index.html',
  'events/index.html',
  'join/index.html',
  'coaches/index.html',
  'faq/index.html',
  'contact/index.html',
  'accessibility/index.html',
]

describe('the exported site carries its stylesheet', () => {
  const stylesheetHref = (html: string) => /<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/.exec(html)?.[1]

  it.each(EXPORTED_PAGES)('%s links a stylesheet', (page) => {
    const html = readFileSync(join(outDirectory, page), 'utf8')
    expect(stylesheetHref(html), `${page} has no <link rel="stylesheet">`).toBeDefined()
  })

  it('links a stylesheet that is actually in the export', () => {
    const html = readFileSync(join(outDirectory, 'index.html'), 'utf8')
    const href = stylesheetHref(html)
    expect(href).toBeDefined()
    expect(existsSync(join(outDirectory, href!.replace(/^\//, '')))).toBe(true)
  })

  it('ships a stylesheet with the design tokens in it, not an empty file', () => {
    const html = readFileSync(join(outDirectory, 'index.html'), 'utf8')
    const css = readFileSync(join(outDirectory, stylesheetHref(html)!.replace(/^\//, '')), 'utf8')
    expect(css.length).toBeGreaterThan(1000)
    // A custom property from tokens.css: proof the whole @import chain was bundled, not just
    // whichever file the layout happened to name.
    expect(css).toMatch(/--[a-z-]+:/)
  })
})

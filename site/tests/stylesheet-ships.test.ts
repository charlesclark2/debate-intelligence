/**
 * The stylesheets have to reach the browser, not merely exist.
 *
 * `v1-e36-t03-site-scaffold` imported `@/styles/globals.css` from the root layout, which is what
 * makes Next emit a stylesheet and link it from every page. `v1-e36-t04-core-pages` dropped that
 * one line, and every build after it exported markup with no CSS at all: correct content, correct
 * headings, correct landmarks, and the default browser stylesheet. It reached the dev preview and
 * was caught by a person looking at it on a phone, not by this suite.
 *
 * Nothing else here could have caught it. `tokens.test.ts` reads the CSS files from disk and
 * checks their contrast, which says nothing about whether they ship. `layout.test.tsx` and
 * `pages-a11y.test.tsx` run axe under jsdom, which has no layout engine and skips colour
 * contrast, so unstyled HTML passes them. So this file asserts the link in the chain none of them
 * covers.
 *
 * Two levels, on purpose:
 *   1. the source imports the stylesheet, which runs on every `pnpm test`;
 *   2. the exported HTML links one and that file is in the export, which runs whenever a build
 *      has produced site/out/ (the same `describe.runIf` pattern pages-a11y.test.tsx uses).
 */

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const outDirectory = join(process.cwd(), 'out')
const hasExport = existsSync(join(outDirectory, 'index.html'))

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

describe('the root layout imports the global stylesheet', () => {
  it('keeps the side-effect import that makes Next emit CSS', () => {
    const layout = readFileSync(join(process.cwd(), 'src/app/layout.tsx'), 'utf8')
    expect(layout).toContain("import '@/styles/globals.css'")
  })

  it('reaches every other stylesheet through it', () => {
    const globals = readFileSync(join(process.cwd(), 'src/styles/globals.css'), 'utf8')
    for (const stylesheet of ['tokens.css', 'layout.css', 'components.css']) {
      expect(globals).toContain(`@import "./${stylesheet}"`)
    }
  })
})

describe.runIf(hasExport)('the exported site carries its stylesheet', () => {
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

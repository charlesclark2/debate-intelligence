import { describe, expect, it } from 'vitest'

// The QA command is plain JavaScript, deliberately: it runs under node with no build step,
// because it is an operator command rather than part of the site. tsconfig has allowJs off, so
// there is no declaration for it and everything imported here is `any`.
// @ts-expect-error - see above
import * as visualQa from '../../scripts/visual-qa.mjs'

import { readExported } from './built-export'

/**
 * The one part of the browser QA command (v1-e36-t08) that reads the export: which pages it
 * visits. tests/visual-qa.test.ts covers the rest of it without a build.
 */
describe('the pages under test', () => {
  it('is every page in the built sitemap, and nothing typed by hand', async () => {
    const paths = await visualQa.pagePaths()
    const sitemap = readExported('sitemap.xml')
    const listed = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (match) => new URL(match[1] as string).pathname,
    )
    expect(paths).toEqual(listed)
    expect(paths).toContain('/')
  })
})

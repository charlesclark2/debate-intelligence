import { describe, expect, it } from 'vitest'

import { exportedFiles, readExported } from './built-export'

/**
 * The contact page as exported: its mailto survives the build and nothing on it collects data
 * (v1-e36-t04 acceptance criterion 4). tests/contact.test.ts checks the same page's sources.
 */
describe('the built contact page', () => {
  it('carries a mailto link and nothing that collects data', () => {
    const html = readExported('contact/index.html')
    expect(html).toContain('href="mailto:charles.clark@wfbschools.com"')
    // The navigation's disclosure button is part of the frame, so only form controls that would
    // collect something are forbidden here.
    for (const pattern of [/<form\b/i, /<input\b/i, /<textarea\b/i, /<select\b/i]) {
      expect(html, `the built contact page contains ${pattern}`).not.toMatch(pattern)
    }
  })

  /**
   * Every file, not just this page: docs/policies/website-publishing.md (Analytics and third
   * parties 7) forbids cookies, localStorage and sessionStorage for any purpose, anywhere on the
   * site, and a call on another page or in a bundle every page loads would break that as surely as
   * one here. This test read only contact/index.html until the v1-e36-t10 review, while its name
   * claimed the whole export.
   */
  it('sets no cookie and uses no browser storage anywhere in the export', () => {
    const files = exportedFiles()
    expect(files.length, 'the export has too few files to be a whole site').toBeGreaterThanOrEqual(50)
    for (const path of files) {
      const content = readExported(path)
      for (const pattern of [/document\.cookie/, /localStorage/, /sessionStorage/]) {
        expect(content, `${path} uses ${pattern}`).not.toMatch(pattern)
      }
    }
  })
})

import { describe, expect, it } from 'vitest'

import { readExported } from './built-export'

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

  it('sets no cookie and uses no browser storage anywhere in the export', () => {
    const html = readExported('contact/index.html')
    for (const pattern of [/document\.cookie/, /localStorage/, /sessionStorage/]) {
      expect(html, `the built contact page uses ${pattern}`).not.toMatch(pattern)
    }
  })
})

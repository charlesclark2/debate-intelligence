import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { loadPage, loadPages, loadSiteSettings } from '@/lib/content'

/**
 * The contact page hands a visitor's message to a coach's school mailbox and to nothing else
 * (v1-e36-t04 acceptance criterion 4).
 *
 * docs/policies/website-publishing.md forbids a form service, a runtime backend and any storage
 * of visitor or parent personal data (Analytics and third parties 6-8, Donations 1). A mailto
 * link is the whole mechanism: the visitor's own mail client sends the message, so nothing about
 * them ever reaches this site, this repository or AWS.
 */

const outDirectory = join(process.cwd(), 'out')
const builtContact = join(outDirectory, 'contact', 'index.html')
const hasExport = existsSync(builtContact)

describe('the contact page', () => {
  const page = loadPage('contact')
  const settings = loadSiteSettings()

  /**
   * guardedHtml, not html: since v1-e36-t07 the page's ways to reach the team live in its
   * at-a-glance block, which is front matter rendered by the route module rather than by Prose.
   * These assertions are about what the page publishes, so they have to read all of what it
   * publishes. Reading the body alone would have quietly stopped checking the addresses the
   * moment they moved into the summary, which is exactly what happened when it did.
   */
  const published = page.guardedHtml

  it('is in the navigation and the sitemap like any other page', () => {
    expect(loadPages().map((candidate) => candidate.slug)).toContain('contact')
    expect(page.route).toBe('/contact/')
  })

  it('links every allowlisted address as a mailto', () => {
    for (const contact of settings.contactEmails) {
      expect(published, `no mailto link for ${contact.address}`).toContain(
        `href="mailto:${contact.address}"`,
      )
    }
  })

  it('publishes no address that is not in the allowlist in content/site.yaml', () => {
    const allowed = new Set(settings.contactEmails.map((contact) => contact.address.toLowerCase()))
    const addresses = published.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) ?? []
    expect(addresses.length).toBeGreaterThan(0)
    for (const address of addresses) {
      expect(allowed.has(address.toLowerCase()), `${address} is not allowlisted`).toBe(true)
    }
  })

  it('has no form, no input and no upload', () => {
    for (const pattern of [/<form\b/i, /<input\b/i, /<textarea\b/i, /<select\b/i, /<button\b/i]) {
      expect(published, `contact.md contains ${pattern}`).not.toMatch(pattern)
    }
  })

  it('names the school as an alternative route without publishing a phone number', () => {
    expect(published).toMatch(/activities\s+office/i)
    expect(published).not.toMatch(/(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]\d{3}[\s.-]\d{4}\b/)
  })

  it('tells a visitor how to have something taken off the site', () => {
    expect(published.toLowerCase()).toMatch(/remov/)
  })
})

describe('the built contact page', () => {
  it.runIf(hasExport)('carries a mailto link and nothing that collects data', () => {
    const html = readFileSync(builtContact, 'utf8')
    expect(html).toContain('href="mailto:charles.clark@wfbschools.org"')
    // The navigation's disclosure button is part of the frame, so only form controls that would
    // collect something are forbidden here.
    for (const pattern of [/<form\b/i, /<input\b/i, /<textarea\b/i, /<select\b/i]) {
      expect(html, `the built contact page contains ${pattern}`).not.toMatch(pattern)
    }
  })

  it.runIf(hasExport)('sets no cookie and uses no browser storage anywhere in the export', () => {
    const html = readFileSync(builtContact, 'utf8')
    for (const pattern of [/document\.cookie/, /localStorage/, /sessionStorage/]) {
      expect(html, `the built contact page uses ${pattern}`).not.toMatch(pattern)
    }
  })
})

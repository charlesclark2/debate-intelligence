import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { loadSiteSettings } from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import { checkPublishingPolicy, withoutScripts } from '@/lib/publishing-policy'

import { builtPageFiles } from './built-export'

/**
 * The content guard over the export (v1-e36-t04 acceptance criterion 3). tests/content-policy.test.ts
 * puts the sources through the same guard; these two read the HTML a visitor downloads, which is
 * where a third-party script or an address added outside site/content/ would actually show up.
 */

const settings = loadSiteSettings()
const consent = loadMediaConsent()

describe('the built export', () => {
  const builtPages = builtPageFiles().map((entry) => ({
    location: entry.location,
    html: readFileSync(entry.path, 'utf8'),
  }))

  it('loads nothing from another origin and embeds no iframe', () => {
    const { errors } = checkPublishingPolicy({ pages: [], settings, consent, builtPages })
    expect(errors).toEqual([])
  })

  it('publishes no address outside the allowlist and no phone number', () => {
    const allowed = new Set(settings.contactEmails.map((contact) => contact.address.toLowerCase()))
    for (const page of builtPages) {
      const text = withoutScripts(page.html)
      for (const address of text.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) ?? []) {
        expect(allowed.has(address.toLowerCase()), `${page.location} publishes ${address}`).toBe(true)
      }
    }
  })
})

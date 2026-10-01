import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { loadSiteSettings } from '@/lib/content'
import { DEFAULT_DEBATER_LOGIN_URL } from '@/lib/feature-flags'

import { builtPageFiles } from './built-export'

/**
 * The export in site/out/ is the artefact that reaches CloudFront, so the absence of the Debater
 * login link is asserted against the real files as well as against a rendered copy
 * (v1-e36-t04 acceptance criterion 4; the rendered copy is tests/login-flag.test.tsx).
 */
describe('the default export', () => {
  const builtPages = builtPageFiles().map((entry) => entry.path)

  // site/out/ must come from a default build, which is what site/scripts/export-checks.sh
  // produces. A build run with SITE_DEBATER_LOGIN=on will, correctly, fail this; and since the
  // build's SITE_* settings are part of what built-export.ts checks, so will running this suite
  // with a different setting from the one the export was built with.
  it('contains no Debater login link on any page', () => {
    const label = loadSiteSettings().debaterLoginLabel
    for (const path of builtPages) {
      const html = readFileSync(path, 'utf8')
      expect(html, `${path} contains the login label`).not.toContain(label)
      expect(html, `${path} links to the V2 app`).not.toContain(`href="${DEFAULT_DEBATER_LOGIN_URL}"`)
    }
  })
})

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SiteNav } from '@/components/SiteNav'
import { loadPages, loadSiteSettings } from '@/lib/content'
import type { FeatureFlagEnvironment } from '@/lib/feature-flags'
import {
  DEFAULT_DEBATER_LOGIN_URL,
  debaterLoginNavigationItem,
  debaterLoginUrl,
  isDebaterLoginEnabled,
} from '@/lib/feature-flags'
import { render, screen } from '@testing-library/react'

/**
 * The Debater login link is built but stays hidden until the V2 authenticated app exists
 * (v1-e36-t04 acceptance criterion 4). The task spec forbids an active login link before then,
 * so the flag is read at build time and defaults to off: when it is off there is no link in the
 * exported HTML at all, not a hidden one, and nothing a visitor or a crawler can find.
 */

const navigationItems = () => loadPages().map((page) => ({ href: page.route, label: page.navLabel }))

describe('the debaterLogin feature flag', () => {
  const offEnvironments: FeatureFlagEnvironment[] = [
    {},
    { SITE_DEBATER_LOGIN: 'off' },
    { SITE_DEBATER_LOGIN: 'true' },
    { SITE_DEBATER_LOGIN: '' },
    { SITE_DEBATER_LOGIN: 'ON' },
  ]

  it.each(offEnvironments)(
    'is off for %o, so an unset or unrecognised value fails closed',
    (env) => {
      expect(isDebaterLoginEnabled(env)).toBe(false)
      expect(debaterLoginNavigationItem('Debater login', env)).toBeNull()
    },
  )

  it('is on only for the exact value "on"', () => {
    const env: FeatureFlagEnvironment = { SITE_DEBATER_LOGIN: 'on' }
    expect(isDebaterLoginEnabled(env)).toBe(true)
    expect(debaterLoginNavigationItem('Debater login', env)).toEqual({
      href: DEFAULT_DEBATER_LOGIN_URL,
      label: 'Debater login',
    })
  })

  it('points at the V2 app under this same domain unless another URL is configured', () => {
    expect(debaterLoginUrl({})).toBe('/app/')
    expect(debaterLoginUrl({ SITE_DEBATER_LOGIN_URL: '/debaters/' })).toBe(
      '/debaters/',
    )
  })
})

describe('the navigation', () => {
  const settings = loadSiteSettings()

  it('renders no Debater login link when the flag is off', () => {
    const items = navigationItems()
    const extra = debaterLoginNavigationItem(settings.debaterLoginLabel, {})
    render(<SiteNav items={extra ? [...items, extra] : items} label={settings.navigationLabel} />)
    expect(screen.queryByRole('link', { name: settings.debaterLoginLabel })).toBeNull()
  })

  it('renders the Debater login link when the flag is on', () => {
    const extra = debaterLoginNavigationItem(settings.debaterLoginLabel, {
      SITE_DEBATER_LOGIN: 'on',
    })
    expect(extra).not.toBeNull()
    render(<SiteNav items={[...navigationItems(), extra!]} label={settings.navigationLabel} />)
    const link = screen.getByRole('link', { name: settings.debaterLoginLabel })
    // next/link normalises the trailing slash away in a bare jsdom render; `trailingSlash: true`
    // in next.config.ts puts it back in the export, which the built-HTML assertions below check.
    expect(link.getAttribute('href')).toMatch(/^\/app\/?$/)
  })
})

/**
 * The export in site/out/ is the artefact that reaches CloudFront, so when one is present the
 * absence of the link is asserted against the real files rather than against a rendered copy.
 */
describe('the default export', () => {
  const outDirectory = join(process.cwd(), 'out')
  const hasExport = existsSync(join(outDirectory, 'index.html'))
  const builtPages = hasExport
    ? readdirSync(outDirectory, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && entry.name !== '_next')
        .map((entry) => join(outDirectory, entry.name, 'index.html'))
        .filter((path) => existsSync(path))
        .concat(join(outDirectory, 'index.html'))
    : []

  // site/out/ must come from a default build, which is what site/scripts/pre-commit-checks.sh
  // produces. A build run with SITE_DEBATER_LOGIN=on will, correctly, fail this.
  it.runIf(hasExport)('contains no Debater login link on any page', () => {
    const label = loadSiteSettings().debaterLoginLabel
    for (const path of builtPages) {
      const html = readFileSync(path, 'utf8')
      expect(html, `${path} contains the login label`).not.toContain(label)
      expect(html, `${path} links to the V2 app`).not.toContain(`href="${DEFAULT_DEBATER_LOGIN_URL}"`)
    }
  })
})

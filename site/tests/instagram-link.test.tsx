import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import ContentPageRoute from '@/app/[slug]/page'
import { SiteFrame } from '@/components/SiteFrame'
import { buildNavigation, instagramLinkSchema, loadSiteSettings } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The link to the team's Instagram account (v1-e37-t07 acceptance criterion 1).
 *
 * Charlie asked for the team's Instagram to be added or embedded. The publishing policy allows a
 * plain text link out to a social account and forbids the vendor's code (Analytics and third
 * parties 4), so what ships is one anchor, in the footer of every page and on the contact page,
 * whose address is in content/site.yaml and whose text says it opens Instagram's site. The built
 * export is checked for every other trace of Instagram or Meta in
 * tests/export/no-third-party-scripts.export-test.ts.
 */

const settings = loadSiteSettings()
const navigation = buildNavigation()
const { instagram } = settings

async function renderRoute(slug: string) {
  const route = await ContentPageRoute({ params: Promise.resolve({ slug }) })
  return render(
    <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
      {route}
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

/** Every link to the configured account inside an element. */
function instagramLinks(container: Element): HTMLAnchorElement[] {
  return [...container.querySelectorAll('a')].filter(
    (link) => link.getAttribute('href') === instagram.address,
  )
}

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? filesUnder(path) : [path]
  })
}

describe('the Instagram settings in content/site.yaml', () => {
  it("are the team's account on www.instagram.com", () => {
    expect(instagram.address).toMatch(/^https:\/\/www\.instagram\.com\/[A-Za-z0-9._]+\/$/)
  })

  it('accept only an account address, and a note that names Instagram', () => {
    const valid = { ...instagram }
    expect(instagramLinkSchema.safeParse(valid).success).toBe(true)
    for (const address of [
      'http://www.instagram.com/team/',
      'https://instagram.com/team/',
      'https://www.instagram.com/p/C0ffee/embed/',
      'https://www.instagram.com/team/embed/',
      'https://www.facebook.com/team/',
      'https://www.instagram.com.example.com/team/',
    ]) {
      expect(instagramLinkSchema.safeParse({ ...valid, address }).success, address).toBe(false)
    }
    expect(
      instagramLinkSchema.safeParse({ ...valid, externalLinkNote: 'opens in a new tab' }).success,
    ).toBe(false)
  })

  it('are the only place the address is written: no source file under src/ names the account', () => {
    const accountPath = new URL(instagram.address).pathname
    for (const path of filesUnder(join(process.cwd(), 'src'))) {
      if (!/\.(?:ts|tsx|css|mjs|js)$/.test(path)) continue
      expect(readFileSync(path, 'utf8'), path).not.toContain(`instagram.com${accountPath}`)
    }
  })
})

describe('the footer of every page', () => {
  it('carries one link to the account, labelled as opening Instagram’s site', () => {
    render(
      <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
        <h1>Page heading</h1>
      </SiteFrame>,
      { container: document.body },
    )
    const footer = screen.getByRole('contentinfo')
    const links = instagramLinks(footer)
    expect(links).toHaveLength(1)
    const link = within(footer).getByRole('link', { name: /opens Instagram's site/i })
    expect(link).toBe(links[0])
    expect(link.textContent).toBe(`${instagram.label} (${instagram.externalLinkNote})`)
  })

  it('makes it an ordinary anchor: no image, icon, script or frame inside it, and no referrer', () => {
    render(
      <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
        <h1>Page heading</h1>
      </SiteFrame>,
      { container: document.body },
    )
    const [link] = instagramLinks(screen.getByRole('contentinfo'))
    expect(link?.children).toHaveLength(0)
    expect(link?.getAttribute('rel')?.split(' ')).toEqual(
      expect.arrayContaining(['noopener', 'noreferrer']),
    )
    // Same tab, as the email-updates link; if a later edit opens a new tab, rel above still holds.
    expect(link?.getAttribute('target')).toBeNull()
  })

  it('keeps it out of the utility navigation, which lists only this site’s pages', () => {
    render(
      <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
        <h1>Page heading</h1>
      </SiteFrame>,
      { container: document.body },
    )
    const footerNav = screen.getByRole('navigation', { name: settings.footerNavigationLabel })
    expect(instagramLinks(footerNav)).toHaveLength(0)
  })
})

describe('the contact page', () => {
  it('carries the link in its body, under its own heading', async () => {
    await renderRoute('contact')
    const main = screen.getByRole('main')
    const links = instagramLinks(main)
    expect(links).toHaveLength(1)
    const section = links[0]!.closest('section') as HTMLElement
    expect(within(section).getByRole('heading', { name: instagram.contactHeading })).toBeDefined()
  })

  it('has no WCAG 2.1 AA violation with the link on it', async () => {
    const { container } = await renderRoute('contact')
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })

  it('is the only Markdown page that carries it outside the footer', async () => {
    await renderRoute('about')
    expect(instagramLinks(screen.getByRole('main'))).toHaveLength(0)
  })
})

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SiteFrame } from '@/components/SiteFrame'
import {
  ContentValidationError,
  buildNavigation,
  loadPages,
  loadSiteSettings,
  parsePage,
} from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * Navigation and footer placement (task v1-e36-t07 acceptance criterion 0).
 *
 * The header navigation used to be every file in content/pages/, ordered by navOrder. That rule
 * reads reasonably and produces a nav nobody chose: the accessibility statement sat between
 * Contact and the end of the bar, not because a parent deciding whether their child joins needs
 * it there, but because it happened to be a file. Any page added later would have appeared in
 * the nav the same way.
 *
 * The nav is now a written-out list in content/site.yaml, and everything else published goes to
 * the footer. The two properties worth defending are that the list is the nav, and that nothing
 * published falls out of both lists and becomes unreachable.
 */

const settings = loadSiteSettings()
const navigation = buildNavigation()
const pages = loadPages()

/** The mobile menu is a client component, so the current route comes from usePathname. */
const pathname = vi.hoisted(() => ({ current: '/' }))
vi.mock('next/navigation', () => ({
  usePathname: () => pathname.current,
}))

beforeEach(() => {
  pathname.current = '/'
})

function renderFrame() {
  return render(
    <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
      <h1>Page heading</h1>
      <p>Body copy.</p>
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

function headerNav() {
  return screen.getByRole('navigation', { name: settings.navigationLabel })
}

function footerNav() {
  return screen.getByRole('navigation', { name: settings.footerNavigationLabel })
}

/**
 * next/link normalises the trailing slash outside a Next build, where the trailingSlash setting
 * in next.config.ts is not in play, so a route written "/accessibility/" renders as
 * "/accessibility" here. The exported files are checked with their real hrefs at the foot of
 * this file; in jsdom the comparison drops the slash on both sides.
 */
const withoutTrailingSlash = (href: string | null) => (href ?? '').replace(/\/+$/, '')

describe('the header navigation is the list in content/site.yaml', () => {
  it('shows exactly the configured pages, in the configured order', () => {
    renderFrame()
    const links = within(headerNav()).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(
      settings.primaryNavigation.map(
        (slug) => pages.find((page) => page.slug === slug)!.navLabel,
      ),
    )
  })

  it('is the pages a parent goes looking for, in the order they need them', () => {
    expect(settings.primaryNavigation).toEqual([
      'home',
      'about',
      'events',
      'join',
      'coaches',
      'faq',
      'contact',
    ])
  })

  it('is no longer every file in content/pages/', () => {
    // The assertion that would have passed under the old rule and has to fail now.
    expect(navigation.primary.length).toBeLessThan(pages.length)
    expect(navigation.utility.length).toBeGreaterThan(0)
  })

  it('does not carry the accessibility statement', () => {
    renderFrame()
    expect(
      within(headerNav()).queryByRole('link', { name: /accessibility/i }),
      'the accessibility statement is back in the header navigation',
    ).toBeNull()
  })
})

describe('the footer carries the utility pages', () => {
  it('links the accessibility statement', () => {
    renderFrame()
    const link = within(footerNav()).getByRole('link', { name: /accessibility/i })
    expect(withoutTrailingSlash(link.getAttribute('href'))).toBe('/accessibility')
  })

  it('carries every published page the header does not', () => {
    renderFrame()
    const inFooter = within(footerNav())
      .getAllByRole('link')
      .map((link) => withoutTrailingSlash(link.getAttribute('href')))
    expect(inFooter).toEqual(
      navigation.utility.map((link) => withoutTrailingSlash(link.href)),
    )
  })

  /**
   * The property that makes an explicit navigation safe to have. Under the old rule a page was
   * reachable because it was a file; under this one it is reachable because it is in one of two
   * lists, and a page left off both would be published and unreachable.
   */
  it('leaves no published page out of both lists', () => {
    const reachable = new Set(
      [...navigation.primary, ...navigation.utility].map((link) => link.href),
    )
    for (const page of pages) {
      expect(reachable.has(page.route), `${page.filePath} is in neither navigation`).toBe(true)
    }
  })
})

describe('the current page is marked', () => {
  it.each(['/', '/join/', '/faq/'])('marks %s with aria-current when it is the page shown', (route) => {
    pathname.current = route
    renderFrame()
    const current = within(headerNav())
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page')
    expect(current, `no link marked current for ${route}`).toHaveLength(1)
    expect(current[0]?.getAttribute('href')?.replace(/\/$/, '')).toBe(route.replace(/\/$/, ''))
  })

  it('marks no link when the page shown is not in the navigation', () => {
    pathname.current = '/accessibility/'
    renderFrame()
    expect(document.querySelectorAll('[aria-current]')).toHaveLength(0)
  })

  it('says it in more than colour', () => {
    // WCAG 2.1 SC 1.4.1: colour alone must not be the only thing carrying the message. The
    // current link takes a rule under it as well as a different colour.
    const layout = readFileSync(join(process.cwd(), 'src/styles/layout.css'), 'utf8').replace(
      /\/\*[\s\S]*?\*\//g,
      '',
    )
    const rule = /(?:^|\})\s*\.site-nav__link--current\s*\{([^}]*)\}/m.exec(layout)?.[1] ?? ''
    expect(rule, '.site-nav__link--current is not in layout.css').not.toBe('')
    expect(rule).toMatch(/border-bottom:/)
  })
})

/**
 * The mobile menu at 390px (acceptance criterion 0).
 *
 * jsdom has no layout engine and no viewport, so a test here cannot see 390 pixels. Two halves
 * of the check can be made here anyway, and they are the two that would regress silently: the
 * behaviour, driven with real keyboard events, and the target sizes, read out of the stylesheet
 * along with the breakpoint that decides when the menu is the menu at all. The look at 390px is
 * the screenshot sweep in v1-e36-t08.
 */
describe('the mobile menu', () => {
  const layout = readFileSync(join(process.cwd(), 'src/styles/layout.css'), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  )

  function ruleBody(selector: string): string {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(?:^|\\}|\\{)\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm').exec(layout)?.[1] ?? ''
  }

  it('is what a 390px phone gets: the toggle only hides from 48rem up', () => {
    // 48rem is 768px, so at 390px the toggle is shown and the list is collapsed behind it.
    const hidden = /@media \(min-width: 48rem\)\s*\{([\s\S]*?)\n\}/.exec(layout)?.[1] ?? ''
    expect(hidden, 'the nav breakpoint block is gone from layout.css').not.toBe('')
    expect(hidden).toContain('.site-nav__toggle')
    expect(hidden).toContain('display: none')
    expect(ruleBody('.site-nav__toggle')).not.toMatch(/display:\s*none/)
  })

  it.each([
    ['.site-nav__toggle', 'the menu button'],
    ['.site-nav__link', 'a navigation link'],
    ['.site-footer__link', 'a footer link'],
  ])('%s meets the 44px target size', (selector) => {
    expect(ruleBody(selector)).toContain('min-height: 44px')
  })

  it('opens the menu to the full width of the screen, with nothing to scroll sideways for', () => {
    const open = ruleBody('.site-nav__list--open')
    expect(open).toContain('left: 0')
    expect(open).toContain('right: 0')
    expect(open, 'the open menu sets a fixed width').not.toMatch(/(?:^|;)\s*width:\s*\d/)
  })

  it('reaches every navigation link by tabbing, in the order the bar reads', async () => {
    const user = userEvent.setup()
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })
    toggle.focus()
    await user.keyboard('{Enter}')

    for (const item of navigation.primary) {
      await user.tab()
      expect(document.activeElement?.tagName).toBe('A')
      expect(document.activeElement?.textContent).toBe(item.label)
    }
  })

  it('closes on Escape and puts focus back on the button that opened it', async () => {
    const user = userEvent.setup()
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })

    toggle.focus()
    await user.keyboard('{Enter}')
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    await user.keyboard('{Escape}')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement, 'Escape left focus adrift').toBe(toggle)
  })

  it('has no WCAG 2.1 AA violation open or closed', async () => {
    const user = userEvent.setup()
    renderFrame()
    await flushPendingEffects()
    let violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])

    await user.click(screen.getByRole('button', { name: /menu/i }))
    violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

/**
 * The build failures. An explicit list is only an improvement if it cannot rot: a renamed page
 * would otherwise leave a nav item pointing nowhere, and nobody would notice until a parent did.
 */
describe('a navigation that does not match the content fails the build', () => {
  const fixture = (name: string) => join(process.cwd(), 'tests/fixtures', name)

  it('builds both lists from the fixture site, nav first and the rest in the footer', () => {
    const fixtureNavigation = buildNavigation(fixture('ordering'))
    expect(fixtureNavigation.primary.map((link) => link.href)).toEqual(['/', '/alpha/'])
    expect(fixtureNavigation.utility.map((link) => link.href)).toEqual(['/zulu/'])
  })

  it('fails, naming the slug, when the navigation lists a page that is not published', () => {
    expect(() => buildNavigation(fixture('navigation-unknown-page'))).toThrowError(
      ContentValidationError,
    )
    expect(() => buildNavigation(fixture('navigation-unknown-page'))).toThrowError(
      /content\/site\.yaml: primaryNavigation lists "ghost", which is not a published page/,
    )
  })

  it('fails when the same page is listed twice', () => {
    expect(() => buildNavigation(fixture('navigation-duplicate'))).toThrowError(
      /content\/site\.yaml: primaryNavigation lists "alpha" twice/,
    )
  })

  it('fails when the navigation and the page itself disagree', () => {
    expect(() => buildNavigation(fixture('navigation-opted-out'))).toThrowError(
      /primaryNavigation lists "alpha", but content\/pages\/alpha\.md sets excludeFromNavigation/,
    )
  })

  it('keeps an opted-out page reachable from the footer', () => {
    const page = parsePage(
      'secret',
      'content/pages/secret.md',
      '---\ntitle: A page\ndescription: A page.\nexcludeFromNavigation: true\n---\n\nCopy.\n',
    )
    expect(page.excludeFromNavigation).toBe(true)
  })
})

/** The built files, which is what a visitor actually gets. */
const outDirectory = join(process.cwd(), 'out')
const hasExport = existsSync(join(outDirectory, 'index.html'))

describe.runIf(hasExport)('the exported navigation', () => {
  const read = (slug: string) =>
    readFileSync(
      slug === 'home' ? join(outDirectory, 'index.html') : join(outDirectory, slug, 'index.html'),
      'utf8',
    )

  const section = (html: string, tag: 'header' | 'footer') =>
    new RegExp(`<${tag}[\\s\\S]*?</${tag}>`).exec(html)?.[0] ?? ''

  it.each(settings.primaryNavigation)('%s marks itself current in the export', (slug) => {
    const route = pages.find((page) => page.slug === slug)!.route
    const header = section(read(slug), 'header')
    expect(header, `${slug} has no header in the export`).not.toBe('')
    const current = [...header.matchAll(/<a[^>]*aria-current="page"[^>]*>/g)]
    expect(current, `${slug} marks no navigation link as the current page`).toHaveLength(1)
    expect(current[0]?.[0]).toContain(`href="${route}"`)
  })

  it.each(settings.primaryNavigation)('%s keeps the utility links in the footer', (slug) => {
    const html = read(slug)
    expect(section(html, 'footer')).toContain('href="/accessibility/"')
    expect(section(html, 'header')).not.toContain('href="/accessibility/"')
  })

  it('marks nothing current on a page outside the navigation', () => {
    expect(section(read('accessibility'), 'header')).not.toContain('aria-current')
  })
})

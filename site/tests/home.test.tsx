import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import { SiteFrame } from '@/components/SiteFrame'
import HomePage from '@/app/page'
import { HOME_SLUG, loadHomeContent, loadPage, loadPages, loadSiteSettings } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The home page (v1-e36-t06 acceptance criterion 2).
 *
 * A parent arriving from the school newsletter has one question, and the page is laid out to
 * answer it before anything else: the October 1 information session. So these assertions are
 * about order and prominence as much as about presence, and about where the words come from.
 *
 * The page is rendered through the real SiteFrame rather than on its own, because the landmark
 * and heading rules axe checks only hold for a whole document.
 */

const page = loadPage(HOME_SLUG)
const content = loadHomeContent()
const settings = loadSiteSettings()
const navigationItems = loadPages().map((item) => ({ href: item.route, label: item.navLabel }))

function renderHome() {
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      <HomePage />
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

describe('the hero', () => {
  it('carries the team name, one line about it and one primary action', () => {
    renderHome()
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toBe(page.title)
    expect(screen.getByText(content.hero.lead)).toBeDefined()

    const action = screen.getByRole('link', { name: content.hero.action.label })
    expect(action.className).toContain('button--primary')
    expect(action.getAttribute('href')).toBe(content.hero.action.href)
  })

  it('has exactly one action, so there is nothing to choose between', () => {
    const { container } = renderHome()
    const hero = container.querySelector('.hero')
    expect(within(hero as HTMLElement).getAllByRole('link')).toHaveLength(1)
  })
})

describe('the October 1 parent session panel', () => {
  it('shows the date, the time, the place and the room', () => {
    renderHome()
    const panel = document.getElementById('parent-session')
    expect(panel, 'no #parent-session panel on the home page').not.toBeNull()
    for (const fact of content.parentSession.facts) {
      expect(within(panel as HTMLElement).getByText(fact.label)).toBeDefined()
      expect(within(panel as HTMLElement).getByText(fact.value)).toBeDefined()
    }
  })

  it('is what the hero action points at', () => {
    renderHome()
    expect(content.hero.action.href).toBe('#parent-session')
    expect(document.getElementById('parent-session')).not.toBeNull()
  })

  it('is the most prominent thing on the page after the hero', () => {
    const { container } = renderHome()
    const sections = [...container.querySelectorAll('main > section')]
    // Second band on the page, directly under the hero.
    expect(sections[1]?.id).toBe('parent-session')
    // And the only one on the inverse surface, which is what makes it outrank the cards below
    // without needing a larger heading than its neighbours.
    const inverse = container.querySelectorAll('.section--inverse')
    expect(inverse).toHaveLength(1)
    expect(inverse[0]?.id).toBe('parent-session')
  })

  it('names itself for a screen reader moving by region', () => {
    renderHome()
    const panel = document.getElementById('parent-session')
    const labelledBy = panel?.getAttribute('aria-labelledby')
    expect(labelledBy).toBe('parent-session-title')
    expect(document.getElementById(labelledBy as string)?.textContent).toBe(
      content.parentSession.title,
    )
  })

  it('lists what a parent will get out of coming', () => {
    renderHome()
    const panel = document.getElementById('parent-session') as HTMLElement
    for (const item of content.parentSession.whatToExpect) {
      expect(within(panel).getByText(item)).toBeDefined()
    }
  })
})

describe('the entry points into the site', () => {
  it('offers between three and five cards', () => {
    const { container } = renderHome()
    const cards = container.querySelectorAll('.card-grid .card')
    expect(cards.length).toBeGreaterThanOrEqual(3)
    expect(cards.length).toBeLessThanOrEqual(5)
    expect(cards).toHaveLength(content.entryPoints.cards.length)
  })

  it('renders the Card component, which before this pass only its own test used', () => {
    const { container } = renderHome()
    expect(container.querySelectorAll('.card').length).toBeGreaterThan(0)
    expect(container.querySelector('.card__title')).not.toBeNull()
  })

  it('links each card to a page that exists on this site', () => {
    renderHome()
    const routes = new Set(loadPages().map((item) => item.route))
    for (const card of content.entryPoints.cards) {
      const link = screen.getByRole('link', { name: card.actionLabel })
      // next/link normalises the trailing slash outside a Next build, where the trailingSlash
      // setting in next.config.ts is not in play, so the href is compared without it.
      expect(link.getAttribute('href')?.replace(/\/$/, '')).toBe(card.href.replace(/\/$/, ''))
      expect(routes, `${card.href} is not a route on this site`).toContain(card.href)
    }
  })

  it('announces the cards as a list, so their number is known before they are read', () => {
    const { container } = renderHome()
    const grid = container.querySelector('.card-grid')
    expect(grid?.tagName).toBe('UL')
    expect(grid?.querySelectorAll(':scope > li')).toHaveLength(content.entryPoints.cards.length)
  })
})

describe('the rest of the page', () => {
  it('renders the prose from content/pages/home.md under its own heading', () => {
    const { container } = renderHome()
    expect(screen.getByRole('heading', { level: 2, name: content.prose.title })).toBeDefined()
    expect(container.querySelector('.prose')?.innerHTML).toBe(page.html)
  })

  it('says what debate builds', () => {
    renderHome()
    expect(
      screen.getByRole('heading', { level: 2, name: content.whatDebateBuilds.title }),
    ).toBeDefined()
    for (const claim of content.whatDebateBuilds.claims) {
      expect(screen.getByRole('heading', { level: 3, name: claim.title })).toBeDefined()
    }
  })
})

/**
 * v1-e36-t06 acceptance criterion 2, second half: every string on the page is read from
 * site/content/, and this test fails if any of it is typed into a component instead. That is the
 * rule the whole site is built on (v1-e36-t03), and a page assembled out of primitives is
 * exactly where it is easiest to break by writing one label inline "for now".
 */
describe('the page holds no copy of its own', () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(join(process.cwd(), directory)).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(join(process.cwd(), path)).isDirectory()) {
        return sourceFiles(path)
      }
      return entry.endsWith('.tsx') || entry.endsWith('.ts') ? [path] : []
    })
  }

  const sources = [...sourceFiles('src/app'), ...sourceFiles('src/components')].map(
    (path) => [path, readFileSync(join(process.cwd(), path), 'utf8')] as const,
  )

  /** Every visible string the home page shows, from both content files. */
  const copy = [
    page.title,
    content.hero.lead,
    content.hero.action.label,
    content.parentSession.eyebrow,
    content.parentSession.title,
    content.parentSession.intro,
    content.parentSession.note,
    content.parentSession.action.label,
    ...content.parentSession.facts.flatMap((fact) => [fact.label, fact.value]),
    ...content.parentSession.whatToExpect,
    content.entryPoints.eyebrow,
    content.entryPoints.title,
    content.entryPoints.intro,
    ...content.entryPoints.cards.flatMap((card) => [card.title, card.body, card.actionLabel]),
    content.prose.eyebrow,
    content.prose.title,
    content.whatDebateBuilds.eyebrow,
    content.whatDebateBuilds.title,
    content.whatDebateBuilds.intro,
    ...content.whatDebateBuilds.claims.flatMap((claim) => [claim.title, claim.body]),
  ]

  it('shows more than a handful of strings, so this test is checking something', () => {
    expect(copy.length).toBeGreaterThan(20)
  })

  it.each(copy.map((text) => [text.slice(0, 48), text] as const))(
    '"%s..." is not written into a component',
    (_label, text) => {
      // A short label such as "Date" is a word any component might legitimately contain, so the
      // comparison is on a distinctive run of the string rather than on the whole of a tiny one.
      if (text.length < 12) {
        return
      }
      for (const [path, source] of sources) {
        expect(source.includes(text), `${path} contains home page copy`).toBe(false)
      }
    },
  )
})

describe('the home page as a whole', () => {
  it('has one h1 and no heading level skipped', () => {
    renderHome()
    expect(document.querySelectorAll('h1')).toHaveLength(1)
    const levels = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number.parseInt(heading.tagName.slice(1), 10),
    )
    for (const [index, level] of levels.entries()) {
      if (index > 0) {
        expect(level, `jumps from h${levels[index - 1]} to h${level}`).toBeLessThanOrEqual(
          (levels[index - 1] as number) + 1,
        )
      }
    }
  })

  it('has no WCAG 2.1 AA violation', async () => {
    renderHome()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

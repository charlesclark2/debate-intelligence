import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import { SiteFrame } from '@/components/SiteFrame'
import { SourceLine } from '@/components/SourceLine'
import HomePage from '@/app/page'
import type { ParentSessionFact } from '@/lib/content'
import {
  HOME_SLUG,
  announcementFields,
  loadHomeContent,
  loadPage,
  loadPages,
  loadSiteSettings,
} from '@/lib/content'

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

/**
 * What the panel shows for one fact: its value, or, while nobody has supplied it, the note that
 * says so. Every fact carries exactly one of the two (parentSessionFactSchema), so this is total.
 */
function factText(fact: ParentSessionFact): string {
  return fact.value ?? fact.unsetNote ?? ''
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
    // next/link normalises the trailing slash outside a Next build.
    expect(action.getAttribute('href')?.replace(/\/$/, '')).toBe(
      content.hero.action.href.replace(/\/$/, ''),
    )
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
      expect(within(panel as HTMLElement).getByText(factText(fact))).toBeDefined()
    }
  })

  /**
   * The room is the fact nobody has supplied yet, and v1-e36-t06 replaced the [[TBD]] marker that
   * used to say so with an ordinary sentence, which left nothing flagging it. A fact is now
   * either a value or an unsetNote, and an unsetNote shows in the same gap badge a [[TBD]] marker
   * does, so the preview a reviewer reads still shows the gap as a gap.
   */
  it('shows an unset fact in the gap badge, not as ordinary copy', () => {
    renderHome()
    const panel = document.getElementById('parent-session') as HTMLElement
    for (const fact of content.parentSession.facts) {
      const shown = within(panel).getByText(factText(fact))
      expect(
        shown.classList.contains('placeholder'),
        `the ${fact.label} fact should ${fact.value ? 'not ' : ''}be in the gap badge`,
      ).toBe(fact.value === undefined)
    }
  })

  it('offers every fact in the panel to the publishing-policy guard as a field', () => {
    const fields = announcementFields()
    expect(fields.map((field) => field.label)).toEqual(
      content.parentSession.facts.map((fact) => fact.label),
    )
    for (const field of fields) {
      expect(field.location).toBe('content/home.yaml')
      expect(field.announcement).toBe(content.parentSession.title)
    }
  })

  /**
   * The hero action used to point here, one screenful above, which asked a visitor to press a
   * button to reach something already in front of them. It now goes to a page, and the panel
   * carries its own action.
   */
  it('is not what the hero action points at, and carries an action of its own', () => {
    renderHome()
    expect(content.hero.action.href).not.toMatch(/^#/)
    const routes = new Set(loadPages().map((item) => item.route))
    expect(routes, `the hero action ${content.hero.action.href} is not a route`).toContain(
      content.hero.action.href,
    )

    const panel = document.getElementById('parent-session') as HTMLElement
    expect(
      within(panel).getByRole('link', { name: content.parentSession.action.label }),
    ).toBeDefined()
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
    const cards = container.querySelectorAll('#start-here .card-grid .card')
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
    const grid = container.querySelector('#start-here .card-grid')
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
 * The academic case (v1-e36-t09 acceptance criteria 1 and 2).
 *
 * What published research found, for the parent whose real question on October 1 is whether a
 * season of this is good for a student academically. It is the last band on the page, after the
 * qualitative "what debate builds" band, and it is built from the same kit as the entry points:
 * Section, CardGrid and one Card per claim. Every claim shows its source on the page, because a
 * research claim about other people's children is only as good as what it rests on.
 */
describe('the academic case band', () => {
  function band(): HTMLElement {
    const section = document.getElementById('academic-case')
    expect(section, 'no #academic-case band on the home page').not.toBeNull()
    return section as HTMLElement
  }

  it('comes after the "what debate builds" band, as the last band on the page', () => {
    const { container } = renderHome()
    const ids = [...container.querySelectorAll('main > section')].map((section) => section.id)
    expect(ids.indexOf('academic-case')).toBe(ids.indexOf('what-debate-builds') + 1)
    expect(ids.at(-1)).toBe('academic-case')
  })

  it('is a Section with one Card per claim in a CardGrid', () => {
    renderHome()
    const section = band()
    expect(section.classList.contains('section')).toBe(true)
    expect(section.getAttribute('aria-labelledby')).toBe('academic-case-title')
    expect(document.getElementById('academic-case-title')?.textContent).toBe(
      content.academicCase.title,
    )
    const grid = section.querySelector('.card-grid')
    expect(grid?.tagName).toBe('UL')
    expect(grid?.querySelectorAll(':scope > li > .card')).toHaveLength(
      content.academicCase.claims.length,
    )
  })

  it('carries between one and five claims, which the loader also enforces', () => {
    expect(content.academicCase.claims.length).toBeGreaterThanOrEqual(1)
    expect(content.academicCase.claims.length).toBeLessThanOrEqual(5)
  })

  it('puts its header on the same left edge as its cards', () => {
    renderHome()
    expect(band().querySelector('.section__header--wide')).not.toBeNull()
  })

  it.each(content.academicCase.claims.map((claim) => [claim.title, claim] as const))(
    '"%s" shows its body and a source line naming who, where, when and what was measured',
    (_title, claim) => {
      renderHome()
      const card = within(band())
        .getByRole('heading', { level: 3, name: claim.title })
        .closest('.card') as HTMLElement
      expect(card, `no card for "${claim.title}"`).not.toBeNull()
      expect(within(card).getByText(claim.body)).toBeDefined()

      const sourceLine = card.querySelector('.source-line')
      expect(sourceLine, `"${claim.title}" has no source line`).not.toBeNull()
      const text = sourceLine?.textContent ?? ''
      expect(text).toContain(content.academicCase.sourceLabel)
      expect(typeof claim.source, `"${claim.title}" still has no source`).toBe('object')
      if (typeof claim.source !== 'string') {
        expect(text).toContain(claim.source.authors)
        expect(text).toContain(claim.source.publication)
        expect(text).toContain(String(claim.source.year))
        expect(text).toContain(claim.source.measured)
      }
    },
  )

  it('shows every source line after the claim it supports', () => {
    renderHome()
    for (const card of band().querySelectorAll('.card')) {
      expect(card.querySelector('.card__body > :last-child')?.classList.contains('source-line')).toBe(
        true,
      )
    }
  })
})

/**
 * The source line on its own, for the two states the shipped content does not currently use: a
 * claim still waiting on its source, and a source that links out of the team site.
 */
describe('a source line', () => {
  const measuredSource = {
    authors: 'Fixture and Example',
    publication: 'Journal of Fixtures',
    year: 2024,
    measured: 'Something measured in a fixture.',
  }

  it('shows the gap badge while the source is still the [[TBD: source]] marker', () => {
    const { container } = render(<SourceLine label="Source" source="[[TBD: source]]" />)
    const badge = container.querySelector('.source-line .placeholder')
    expect(badge?.textContent).toBe('TBD')
    expect(container.textContent).not.toContain('[[TBD')
  })

  it('says a link to the source leaves the team site', () => {
    render(
      <SourceLine
        externalLinkNote="opens a site outside the team's"
        label="Source"
        source={{ ...measuredSource, href: 'https://example.org/study' }}
      />,
    )
    const link = screen.getByRole('link')
    expect(link.getAttribute('href')).toBe('https://example.org/study')
    expect(link.textContent).toContain(measuredSource.publication)
    expect(link.textContent).toContain("opens a site outside the team's")
  })

  it('shows the publication as a citation without a link when there is none', () => {
    const { container } = render(<SourceLine label="Source" source={measuredSource} />)
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('cite')?.textContent).toBe(measuredSource.publication)
  })
})

/**
 * The source line is small text, so it is body grey. The muted grey and the warm accent measure
 * under 4.5:1 on the card's panel tint and are large-text only (tokens.css). And nothing in the
 * band can push a 390px screen sideways: no fixed width and no nowrap, so a long citation wraps.
 */
describe('the academic case styles', () => {
  const sectionsCss = readFileSync(join(process.cwd(), 'src/styles/sections.css'), 'utf8')
  const sourceLineRules = [...sectionsCss.matchAll(/(\.source-line[^{]*|#academic-case[^{]*)\{([^}]*)\}/g)]

  it('styles the source line', () => {
    expect(sourceLineRules.length).toBeGreaterThan(0)
  })

  it('paints the source line body grey', () => {
    const base = sourceLineRules.find((rule) => rule[1]?.trim() === '.source-line')
    expect(base?.[2]).toMatch(/(?<!-)color:\s*var\(--color-text-body\)/)
  })

  it('never paints it with a restricted colour', () => {
    for (const rule of sourceLineRules) {
      expect(rule[2]).not.toMatch(/--color-(?:text-muted|brand-warm)/)
    }
  })

  it('sets no fixed width, no nowrap and no transition', () => {
    for (const rule of sourceLineRules) {
      expect(rule[2]).not.toMatch(/(?:^|[\s;])(?:min-)?width\s*:/)
      expect(rule[2]).not.toMatch(/white-space\s*:\s*nowrap/)
      expect(rule[2]).not.toMatch(/transition|animation/)
    }
  })
})

/**
 * v1-e36-t09 acceptance criterion 5: a parent who presses a card lands on a heading that matches
 * what they pressed. The loader enforces it at build time (tests/content.test.ts has the failing
 * cases); this is the shipped content, checked against the pages it opens.
 */
describe('each entry-point card', () => {
  const pagesByRoute = new Map(loadPages().map((item) => [item.route, item]))

  it.each(content.entryPoints.cards.map((card) => [card.href, card] as const))(
    '%s is labelled with the title of the page it opens',
    (href, card) => {
      const destination = pagesByRoute.get(href)
      expect(destination, `${href} is not a page`).toBeDefined()
      expect(card.title).toBe(destination?.title)
    },
  )
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
    ...content.parentSession.facts.flatMap((fact) => [fact.label, factText(fact)]),
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
    content.academicCase.eyebrow,
    content.academicCase.title,
    content.academicCase.intro,
    content.academicCase.sourceLabel,
    ...(content.academicCase.externalLinkNote ? [content.academicCase.externalLinkNote] : []),
    ...content.academicCase.claims.flatMap((claim) => [
      claim.title,
      claim.body,
      ...(typeof claim.source === 'string'
        ? []
        : [claim.source.authors, claim.source.publication, claim.source.measured]),
    ]),
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

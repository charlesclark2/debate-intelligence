import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import EventsPage from '@/app/events/page'
import { SiteFrame } from '@/components/SiteFrame'
import {
  EVENTS_SLUG,
  EVENT_COMPARISON_FIELDS,
  findPlaceholders,
  loadEventsContent,
  loadPage,
  loadPages,
  loadSiteSettings,
} from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * What the events are (task v1-e36-t07 acceptance criterion 3).
 *
 * The question this page exists to answer in a few seconds is "how are these three different?".
 * Twelve hundred words under three headings never answered it, because the facts that separate
 * Public Forum from Lincoln-Douglas from Policy were spread through the paragraphs explaining
 * each one. The comparison is the fix, and a comparison only works if it is genuinely parallel:
 * the same four fields, in the same order, in all three cards, with the detail underneath rather
 * than inside them.
 *
 * So most of these assertions are about sameness. A card that quietly drops a field, or answers
 * a different field from its neighbours, is the failure they exist to catch.
 */

const page = loadPage(EVENTS_SLUG)
const content = loadEventsContent()
const settings = loadSiteSettings()
const navigationItems = loadPages().map((item) => ({ href: item.route, label: item.navLabel }))

const COMPARISON_FIELD_COUNT = 4

function renderEvents() {
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      <EventsPage />
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

function comparisonCards(): HTMLElement[] {
  return [...document.querySelectorAll('.card-grid .card')] as HTMLElement[]
}

describe('the three events are shown as parallel cards', () => {
  it('names Public Forum, Lincoln-Douglas and Policy, in that order', () => {
    expect(content.events.map((event) => event.id)).toEqual([
      'public-forum',
      'lincoln-douglas',
      'policy',
    ])
    renderEvents()
    const cards = comparisonCards()
    expect(cards).toHaveLength(content.events.length)
    expect(cards.map((card) => card.querySelector('.card__title')?.textContent)).toEqual(
      content.events.map((event) => event.name),
    )
  })

  it('lays them out as a grid of cards, one item per event', () => {
    renderEvents()
    const grid = document.querySelector('.card-grid')
    expect(grid?.tagName).toBe('UL')
    expect(grid?.className).toContain('card-grid--3-up')
    expect(grid?.querySelectorAll(':scope > li.card-grid__item')).toHaveLength(
      content.events.length,
    )
  })

  it('opens every card with one line saying what that event asks', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      expect(within(card).getByText(event.summary)).toBeDefined()
    }
  })
})

describe('the comparison is genuinely a comparison', () => {
  it('gives every card the same four fields, in the same order', () => {
    expect(EVENT_COMPARISON_FIELDS).toHaveLength(COMPARISON_FIELD_COUNT)
    renderEvents()
    const expectedLabels = EVENT_COMPARISON_FIELDS.map((field) => content.comparisonLabels[field])

    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const list = card.querySelector('.event-comparison')
      expect(list?.tagName, `${event.name} has no comparison list`).toBe('DL')

      const labels = [...(list?.querySelectorAll('dt') ?? [])].map((term) => term.textContent)
      const values = [...(list?.querySelectorAll('dd') ?? [])].map((value) => value.textContent)
      expect(labels, `${event.name} field labels`).toEqual(expectedLabels)
      expect(values, `${event.name} field values`).toEqual(
        EVENT_COMPARISON_FIELDS.map((field) => event.comparison[field]),
      )
    }
  })

  it('fills all four fields for every event, so no card has a hole in it', () => {
    for (const event of content.events) {
      for (const field of EVENT_COMPARISON_FIELDS) {
        expect(event.comparison[field].trim().length, `${event.name}.${field}`).toBeGreaterThan(0)
      }
    }
  })

  it('says something different in each card, so the comparison is worth reading', () => {
    for (const field of EVENT_COMPARISON_FIELDS) {
      const values = content.events.map((event) => event.comparison[field])
      expect(
        new Set(values).size,
        `every event gives the same answer for ${field}, which tells a parent nothing`,
      ).toBeGreaterThan(1)
    }
  })
})

/**
 * The topic each event is arguing right now, which Charlie maintains through the season.
 *
 * It is deliberately not a fifth comparison field: the four fields describe how an event works
 * and do not change, and this one has a shelf life measured in weeks. Mixing them would make the
 * whole block look stale the moment a Public Forum topic rolled over.
 */
describe('the topic each event is arguing right now', () => {
  it('shows one on every card, under the same label', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const topic = card.querySelector('.event-topic')
      expect(topic, `${event.name} has no current topic`).not.toBeNull()
      expect(within(topic as HTMLElement).getByText(content.currentTopicLabel)).toBeDefined()
      expect((topic as HTMLElement).textContent?.trim().length).toBeGreaterThan(
        content.currentTopicLabel.length,
      )
    }
  })

  it('keeps it out of the four comparison fields, which stay four', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const list = card.querySelector('.event-comparison')
      expect(list?.querySelectorAll('dt'), `${event.name}`).toHaveLength(COMPARISON_FIELD_COUNT)
      expect((list as HTMLElement).textContent).not.toContain(content.currentTopicLabel)
    }
  })

  /**
   * A topic nobody has supplied yet is a [[TBD]] marker, not a blank. It renders as the visible
   * placeholder badge on a dev preview and src/lib/publishing-policy.ts fails a prod build while
   * it is there, so the site cannot go live telling a parent nothing about what is being argued.
   */
  it('marks an unsupplied topic as a placeholder rather than leaving a hole', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const topic = card.querySelector('.event-topic') as HTMLElement
      const placeholders = findPlaceholders(event.currentTopic)
      if (placeholders.length > 0) {
        expect(topic.querySelector('.placeholder'), `${event.name} placeholder badge`).not.toBeNull()
        for (const note of placeholders) {
          expect(note.length, `${event.name} placeholder has no note saying what is needed`)
            .toBeGreaterThan(0)
        }
      } else {
        expect(topic.querySelector('.placeholder'), `${event.name}`).toBeNull()
        expect(topic.textContent).toContain(event.currentTopic.replace(/\s+/g, ' ').trim())
      }
    }
  })
})

describe('the detail sits beneath the comparison, not inside it', () => {
  it('gives each event a detail section of its own, in the order of the cards', () => {
    renderEvents()
    for (const event of content.events) {
      const section = document.getElementById(event.id)
      expect(section, `no detail section for ${event.name}`).not.toBeNull()
      expect(section?.getAttribute('aria-labelledby')).toBe(`${event.id}-title`)
      expect(screen.getByRole('heading', { level: 2, name: event.name })).toBeDefined()
    }
  })

  it('links each card down to its own detail section, with a label that names the event', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const link = within(card).getByRole('link', { name: event.detailActionLabel })
      expect(link.getAttribute('href')).toBe(`#${event.id}`)
    }
    // Three links reading the same words but going to three different places is a set of links a
    // screen-reader user cannot tell apart when they are listed out of context.
    const labels = content.events.map((event) => event.detailActionLabel)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('keeps the card compact: the full explanation is not in it', () => {
    renderEvents()
    for (const [index, event] of content.events.entries()) {
      const card = comparisonCards()[index] as HTMLElement
      const detailStart = event.detail.replace(/\s+/g, ' ').trim().slice(0, 60)
      expect(
        (card.textContent ?? '').replace(/\s+/g, ' ').includes(detailStart),
        `the ${event.name} card holds the whole explanation instead of the comparison`,
      ).toBe(false)
    }
  })

  it('shows the full explanation of every event on the page', () => {
    renderEvents()
    for (const event of content.events) {
      const section = document.getElementById(event.id) as HTMLElement
      const rendered = (section.textContent ?? '').replace(/\s+/g, ' ')
      const firstSentence = event.detail
        .split('\n\n')[0]!
        .replace(/\s+/g, ' ')
        .replace(/\*\*/g, '')
        .trim()
      expect(rendered.includes(firstSentence.slice(0, 60)), `${event.name} detail`).toBe(true)
    }
  })
})

describe('what is true of all three, and what closes the page', () => {
  it('lays the three out in one row rather than two and then one', () => {
    renderEvents()
    const list = document.querySelector('#true-of-all-three .claim-list')
    expect(list?.className, 'the shared truths use the default 2-up claim list').toContain(
      'claim-list--three-across',
    )
    expect(list?.querySelectorAll(':scope > li')).toHaveLength(content.sharedTruths.items.length)
  })

  it('says three of what, rather than leaving the heading to be guessed', () => {
    // A heading that counts things has to name them: "True of all three" on its own asks the
    // reader to work out three of what, on a page that has not yet listed the three.
    expect(content.sharedTruths.title.toLowerCase()).toContain('event')
  })

  it('leads with the things a parent does not have to check event by event', () => {
    renderEvents()
    const band = document.getElementById('true-of-all-three')
    expect(band, 'no band for what is true of all three events').not.toBeNull()
    expect(screen.getByRole('heading', { level: 2, name: content.sharedTruths.title })).toBeDefined()
    for (const item of content.sharedTruths.items) {
      expect(within(band as HTMLElement).getByRole('heading', { name: item.title })).toBeDefined()
      expect(within(band as HTMLElement).getByText(item.body)).toBeDefined()
    }
  })

  it('keeps cross-examination and prep time, the judge, and a tournament day', () => {
    expect(content.closingSections.map((section) => section.id)).toEqual([
      'cross-examination-and-prep-time',
      'what-the-judge-does',
      'a-tournament-day',
    ])
    renderEvents()
    for (const section of content.closingSections) {
      const band = document.getElementById(section.id)
      expect(band, `no section for "${section.title}"`).not.toBeNull()
      expect(screen.getByRole('heading', { level: 2, name: section.title })).toBeDefined()
    }
  })
})

/**
 * Acceptance criterion 3, second half: at 390px the comparison stacks and nothing runs off the
 * side of the screen. jsdom has no layout engine, so what is checked here is the source of the
 * rules that decide it. The pixel confirmation is the screenshot sweep in v1-e36-t08.
 */
describe('the comparison stacks on a phone with nothing to scroll sideways for', () => {
  const sections = readFileSync(join(process.cwd(), 'src/styles/sections.css'), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  )

  function ruleBody(selector: string): string | null {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm').exec(sections)?.[1] ?? null
  }

  it('gives the grid its columns only inside a min-width media query', () => {
    // The base .card-grid rule is one column. Every multi-column rule for it is inside a
    // min-width query, so 390px never gets a second column.
    expect(ruleBody('.card-grid')).not.toMatch(/grid-template-columns/)
    for (const match of sections.matchAll(/\.card-grid--\d-up\s*\{/g)) {
      const before = sections.slice(0, match.index)
      const lastQuery = before.lastIndexOf('@media')
      expect(lastQuery, 'a card-grid column rule sits outside any media query').toBeGreaterThan(-1)
      expect(before.slice(lastQuery)).toMatch(/min-width/)
    }
  })

  it('stacks each comparison label above its value rather than beside it', () => {
    // A two-column label/value grid would size its first column to the longest label in the set,
    // which is what pushes a card past the width of a 390px screen.
    expect(ruleBody('.event-comparison')).not.toMatch(/grid-template-columns/)
  })

  it('lets every value wrap, declaring no fixed width and no nowrap', () => {
    for (const selector of ['.event-comparison', '.event-comparison__label', '.event-comparison__value', '.event-card__summary']) {
      const body = ruleBody(selector)
      expect(body, `${selector} is not in sections.css`).not.toBeNull()
      expect(body, `${selector} stops its text wrapping`).not.toMatch(/white-space:\s*nowrap/)
      expect(body, `${selector} sets a fixed width`).not.toMatch(/(?:^|;)\s*width:\s*\d/)
      expect(body, `${selector} sets a fixed minimum width`).not.toMatch(/min-width:\s*\d/)
    }
  })

  it('uses the body grey for the small field labels, never the large-text-only muted grey', () => {
    // #74798E reaches 4.31:1 on white, which is large text and non-text only (tokens.css). A
    // 14px uppercase label is neither.
    expect(ruleBody('.event-comparison__label')).toContain('color: var(--color-text-body)')
  })
})

describe('the events page as a whole', () => {
  it('has one h1, which is the page title from the content file', () => {
    renderEvents()
    const headings = document.querySelectorAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0]?.textContent).toBe(page.title)
  })

  it('skips no heading level', () => {
    renderEvents()
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
    renderEvents()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

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

  const copy = [
    ...EVENT_COMPARISON_FIELDS.map((field) => content.comparisonLabels[field]),
    content.currentTopicLabel,
    content.sharedTruths.title,
    ...content.sharedTruths.items.flatMap((item) => [item.title, item.body]),
    content.comparisonTitle,
    content.comparisonIntro,
    ...content.events.flatMap((event) => [
      event.name,
      event.summary,
      event.detailActionLabel,
      event.currentTopic,
      ...EVENT_COMPARISON_FIELDS.map((field) => event.comparison[field]),
      event.detail,
    ]),
    ...content.closingSections.flatMap((section) => [section.title, section.body]),
  ]

  it('shows more than a handful of strings, so this test is checking something', () => {
    expect(copy.length).toBeGreaterThan(20)
  })

  it.each(copy.map((text) => [text.slice(0, 48).replace(/\s+/g, ' '), text] as const))(
    '"%s..." is not written into a component',
    (_label, text) => {
      if (text.length < 12) {
        return
      }
      for (const [path, source] of sources) {
        expect(source.includes(text.trim()), `${path} contains events page copy`).toBe(false)
      }
    },
  )
})

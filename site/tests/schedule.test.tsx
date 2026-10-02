import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, within } from '@testing-library/react'
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SchedulePage from '@/app/schedule/page'
import { SiteFrame } from '@/components/SiteFrame'
import { SCHEDULE_SLUG, buildNavigation, loadPage, loadSiteSettings } from '@/lib/content'
import { loadScheduleContent, loadScheduleView } from '@/lib/tournaments'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The /schedule/ page (v1-e37-t02 acceptance criterion 2), rendered through the real frame.
 *
 * What a parent must not be misled about, each asserted on what the page shows: two tournaments
 * on the same dates are both there and both marked; a tournament debated online from the high
 * school says so; a conditional tournament shows its condition, not just a badge; and the page
 * lists the whole season whatever day it was built.
 */

const settings = loadSiteSettings()
const navigation = buildNavigation()
const content = loadScheduleContent()
const page = loadPage(SCHEDULE_SLUG)

afterEach(() => {
  vi.unstubAllEnvs()
})

function renderSchedule() {
  return render(
    <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
      <SchedulePage />
    </SiteFrame>,
    { container: document.body },
  )
}

async function flushPendingEffects() {
  await act(async () => {})
}

const entry = (id: string) => {
  const element = document.getElementById(id)
  if (!element) throw new Error(`no entry #${id} on the page`)
  return element
}

/** The value beside a label in an entry's fact list. */
function fact(id: string, label: string): string {
  const terms = [...entry(id).querySelectorAll('dt')]
  const term = terms.find((candidate) => candidate.textContent === label)
  if (!term) throw new Error(`#${id} has no "${label}"`)
  return term.nextElementSibling?.textContent ?? ''
}

describe('the whole season, in date order, with nationals apart', () => {
  it('lists the season in the order worked out by hand from the schedule document', () => {
    renderSchedule()
    const season = document.getElementById('season') as HTMLElement
    expect([...season.querySelectorAll('.schedule-entry')].map((element) => element.id)).toEqual([
      'neenah-2026',
      'fort-atkinson-2026',
      'iowa-caucus-2026',
      'ronald-reagan-2026',
      'west-bend-online-2026',
      'west-bend-2026',
      'minneapple-2026',
      'badgerland-2026',
      'brookfield-east-2026',
      'glenbrooks-2026',
      'whitefish-bay-home-2026',
      'marquette-2026',
      'blake-2026',
      'madison-west-2027',
      'last-chance-qualifier-2027',
      'southern-wisconsin-nsda-qualifier-2027',
      'wisconsin-state-2027',
      'milwaukee-ncfl-qualifier-2027',
    ])
  })

  it('gives nationals a section of their own, after the season', () => {
    renderSchedule()
    const nationals = document.getElementById('nationals') as HTMLElement
    expect(within(nationals).getByRole('heading', { level: 2 }).textContent).toBe(content.nationalsTitle)
    expect([...nationals.querySelectorAll('.schedule-entry')].map((element) => element.id)).toEqual([
      'ncfl-nationals-2027',
      'nsda-nationals-2027',
    ])
    const sections = [...document.querySelectorAll('main > section')].map((section) => section.id)
    expect(sections.indexOf('nationals')).toBeGreaterThan(sections.indexOf('season'))
  })

  it('uses an ordered list, so a screen reader announces how many tournaments there are', () => {
    renderSchedule()
    const list = document.querySelector('#season .schedule-list')
    expect(list?.tagName).toBe('OL')
    expect(list?.querySelectorAll(':scope > li')).toHaveLength(18)
  })

  it('shows a tournament that has already happened exactly as one that has not', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2027-07-01T12:00:00Z'))
    try {
      renderSchedule()
      expect(entry('neenah-2026').textContent).toContain('Saturday, October 10, 2026')
      expect(document.querySelectorAll('.schedule-entry')).toHaveLength(20)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('each entry', () => {
  it('shows its dates, name, place, how it is held, events, overnight and status', () => {
    renderSchedule()
    const minneapple = entry('minneapple-2026')
    expect(within(minneapple).getByRole('heading', { level: 3 }).textContent).toBe('MinneApple')
    expect(minneapple.querySelector('.schedule-entry__dates')?.textContent).toBe(
      'Saturday, November 7 to Monday, November 9, 2026',
    )
    expect(fact('minneapple-2026', content.labels.where)).toBe('Apple Valley High School, Minnesota')
    expect(fact('minneapple-2026', content.labels.held)).toBe('In person')
    expect(fact('minneapple-2026', content.labels.events)).toBe('Public Forum, Lincoln-Douglas')
    expect(fact('minneapple-2026', content.labels.overnight)).toBe('Yes')
    expect(fact('minneapple-2026', content.labels.status)).toBe('Confirmed')
    expect(fact('minneapple-2026', content.labels.notes)).toBe('Varsity only.')
  })

  it('shows a sign-up-by date where one is set, and no empty row where none is', () => {
    const view = loadScheduleView()
    const neenah = view.seasonTournaments.find((tournament) => tournament.id === 'neenah-2026')!
    expect(view.facts(neenah).map((row) => row.key)).not.toContain('signUpBy')
    const facts = view.facts({ ...neenah, signUpBy: '2026-10-03' })
    expect(facts.find((row) => row.key === 'signUpBy')).toEqual({
      key: 'signUpBy',
      label: content.labels.signUpBy,
      value: 'Saturday, October 3, 2026',
    })
  })

  it('says a tournament debated online is debated at the high school, never just "online"', () => {
    renderSchedule()
    for (const id of ['iowa-caucus-2026', 'west-bend-online-2026']) {
      expect(fact(id, content.labels.held)).toBe('Online, debated at Whitefish Bay High School')
    }
    const heldValues = [...document.querySelectorAll('.schedule-entry dd')].map((dd) => dd.textContent?.trim())
    expect(heldValues).not.toContain('Online')
  })

  it('says how each event at Glenbrooks is held, because they differ', () => {
    renderSchedule()
    expect(fact('glenbrooks-2026', content.labels.events)).toBe(
      'Public Forum, Lincoln-Douglas, Policy debate',
    )
    expect(fact('glenbrooks-2026', 'Public Forum, Lincoln-Douglas')).toBe(
      'Online, debated at Whitefish Bay High School. Overnight: No.',
    )
    expect(fact('glenbrooks-2026', 'Policy debate')).toBe('In person, Glenview, Illinois. Overnight: Yes.')
  })

  it('shows the condition of a conditional tournament in full, beside its badge', () => {
    renderSchedule()
    const home = entry('whitefish-bay-home-2026')
    expect(home.querySelector('.status-badge')?.textContent).toBe('Conditional')
    expect(home.querySelector('.schedule-entry__condition')?.textContent).toBe(
      'Our team hosts this tournament. Our students compete in it only if enough families volunteer ' +
        'to help run it and some students still need qualifying results, called legs, for the state ' +
        'tournament.',
    )
  })

  it('marks a tentative tournament as tentative', () => {
    renderSchedule()
    expect(entry('milwaukee-ncfl-qualifier-2027').querySelector('.status-badge')?.textContent).toBe('Tentative')
    expect(fact('milwaukee-ncfl-qualifier-2027', content.labels.where)).toBe('To be announced')
  })
})

describe('tournaments on the same dates', () => {
  const pairs: Array<[string, string, string]> = [
    ['iowa-caucus-2026', 'ronald-reagan-2026', 'Ronald Reagan High School'],
    ['ronald-reagan-2026', 'iowa-caucus-2026', 'Iowa Caucus'],
    ['west-bend-2026', 'minneapple-2026', 'MinneApple'],
    ['minneapple-2026', 'west-bend-2026', 'West Bend High School'],
    ['brookfield-east-2026', 'glenbrooks-2026', 'Glenbrooks'],
    ['glenbrooks-2026', 'brookfield-east-2026', 'Brookfield East High School'],
    ['southern-wisconsin-nsda-qualifier-2027', 'last-chance-qualifier-2027', 'Last Chance Qualifier'],
    ['last-chance-qualifier-2027', 'southern-wisconsin-nsda-qualifier-2027', 'Southern Wisconsin NSDA Qualifier'],
  ]

  it.each(pairs)('%s says in words that it shares dates with %s, and links to it', (id, other, name) => {
    renderSchedule()
    const marker = entry(id).querySelector('.schedule-entry__overlap') as HTMLElement
    expect(marker, `${id} carries no overlap marker`).not.toBeNull()
    expect(marker.textContent).toContain(`${content.labels.overlap}:`)
    const link = within(marker).getByRole('link', { name })
    expect(link.getAttribute('href')).toBe(`#${other}`)
    expect(entry(id).classList.contains('schedule-entry--overlap')).toBe(true)
  })

  it('marks exactly those eight entries and no others', () => {
    renderSchedule()
    const marked = [...document.querySelectorAll('.schedule-entry')]
      .filter((element) => element.querySelector('.schedule-entry__overlap'))
      .map((element) => element.id)
      .sort()
    expect(marked).toEqual(pairs.map(([id]) => id).sort())
  })
})

describe('subscribing', () => {
  it('offers the calendar as a webcal:// subscription and as the plain https address', () => {
    vi.stubEnv('SITE_URL', 'https://wfbdebate.example.invalid')
    renderSchedule()
    const band = document.getElementById('subscribe') as HTMLElement
    const subscribe = within(band).getByRole('link', { name: content.subscribe.subscribeLabel })
    expect(subscribe.getAttribute('href')).toBe('webcal://wfbdebate.example.invalid/schedule.ics')
    const address = within(band).getByRole('link', { name: 'https://wfbdebate.example.invalid/schedule.ics' })
    expect(address.getAttribute('href')).toBe('https://wfbdebate.example.invalid/schedule.ics')
    for (const step of content.subscribe.steps) {
      expect(within(band).getByText(step)).toBeDefined()
    }
  })

  it('says when the schedule was last updated', () => {
    renderSchedule()
    expect(document.querySelector('.schedule-revised')?.textContent).toBe(
      `${content.labels.revised}: Thursday, October 1, 2026`,
    )
  })
})

describe('reaching the page', () => {
  it('is in the primary navigation, straight after the events', () => {
    expect(settings.primaryNavigation.indexOf(SCHEDULE_SLUG)).toBe(
      settings.primaryNavigation.indexOf('events') + 1,
    )
    expect(navigation.primary.map((link) => link.href)).toContain(page.route)
  })
})

describe('the page as a whole', () => {
  it('has one h1 and no heading level skipped', () => {
    renderSchedule()
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
    renderSchedule()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

/**
 * Every word on the page comes from content/, as on every other page: the route module and the
 * calendar route hold none of it.
 */
describe('the page holds no copy of its own', () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(join(process.cwd(), directory)).flatMap((name) => {
      const path = join(directory, name)
      if (statSync(join(process.cwd(), path)).isDirectory()) {
        return sourceFiles(path)
      }
      return name.endsWith('.tsx') || name.endsWith('.ts') ? [path] : []
    })
  }

  const sources = [...sourceFiles('src/app'), ...sourceFiles('src/components'), 'src/lib/icalendar.ts'].map(
    (path) => [path, readFileSync(join(process.cwd(), path), 'utf8')] as const,
  )

  const copy = [
    page.title,
    content.subscribe.title,
    content.subscribe.intro,
    content.subscribe.subscribeLabel,
    content.subscribe.linkLabel,
    ...content.subscribe.steps,
    content.seasonIntro,
    content.nationalsIntro,
    content.held['online-at-school'],
    content.calendar.name,
    content.calendar.description,
  ]

  it.each(copy.map((text) => [text.slice(0, 48), text] as const))(
    '"%s..." is not written into a component',
    (_label, text) => {
      for (const [path, source] of sources) {
        expect(source.includes(text.trim()), `${path} contains schedule page copy`).toBe(false)
      }
    },
  )
})

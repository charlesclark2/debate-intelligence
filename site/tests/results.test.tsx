import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomePage from '@/app/page'
import ResultsPage from '@/app/results/page'
import { SiteFrame } from '@/components/SiteFrame'
import {
  RESULTS_SLUG,
  buildNavigation,
  loadHomeContent,
  loadPage,
  loadSiteSettings,
} from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import { checkPublishingPolicy } from '@/lib/publishing-policy'
import {
  PLACINGS,
  loadResults,
  loadResultsView,
  newestResults,
  placingProblem,
  resultLine,
  resultsGuardedContent,
} from '@/lib/results'
import type { Results } from '@/lib/results'
import { loadSchedule } from '@/lib/tournaments'

import { describeViolations, findAccessibilityViolations } from './axe'
import { replaceOnce } from './schedule-fixture'
import {
  SEASON_FIXTURE,
  STUDENTS,
  oneResult,
  resultsContent,
  resultsSiteRoot,
} from './results-fixture'

/**
 * The season's results (v1-e37-t06): content/results.yaml, the /results/ page and the three
 * newest on the home page, held to docs/policies/website-publishing.md, Results and awards.
 *
 * Every name below is invented (Students 11). The expected page is written out by hand from
 * SEASON_FIXTURE in tests/results-fixture.ts, not taken from the loader's output, so a loader
 * that dropped a placing, put the tournaments in the wrong order or printed a name it should not
 * have cannot agree with it by construction (working agreement 6).
 */

afterEach(() => {
  vi.restoreAllMocks()
})

function loadError(directory: string): string {
  try {
    loadResults(directory)
  } catch (error) {
    return (error as Error).message
  }
  throw new Error('expected content/results.yaml to be rejected, and it loaded')
}

/** The lines of a loaded season, tournament by tournament, as the page prints them. */
function lines(results: Results): Array<[string, string[]]> {
  return results.groups.map((group) => [group.tournament.name, group.results.map(resultLine)])
}

/*
 * What the page shows for SEASON_FIXTURE, worked out by hand. Badgerland ends on November 14,
 * West Bend is November 7, Fort Atkinson October 17 and Neenah October 3, so that is the order.
 */
const EXPECTED_GROUPS: Array<[string, string, string[]]> = [
  [
    'Badgerland',
    'Friday, November 13 to Saturday, November 14, 2026',
    ['Second speaker, Junior Varsity Lincoln-Douglas: a Whitefish Bay debater'],
  ],
  [
    'West Bend High School',
    'Saturday, November 7, 2026',
    ['Quarterfinalist, Novice Public Forum: Sam Okafor (2027) and Avery Chen (2029)'],
  ],
  [
    'Fort Atkinson',
    'Saturday, October 17, 2026',
    [
      'First place, Varsity Lincoln-Douglas: Jordan Rivera (2028)',
      'Top speaker, Varsity Lincoln-Douglas: Jordan Rivera (2028)',
    ],
  ],
  ['Neenah', 'Saturday, October 3, 2026', ['Semifinalist, Varsity Policy debate: a Whitefish Bay team']],
]

describe('content/results.yaml, loaded', () => {
  const results = loadResults(resultsContent(SEASON_FIXTURE))

  it('groups the placings by tournament, newest tournament first', () => {
    expect(lines(results)).toEqual(EXPECTED_GROUPS.map(([name, , placings]) => [name, placings]))
  })

  it('takes a scheduled tournament’s name and dates from content/tournaments.yaml', () => {
    const westBend = results.groups.find((group) => group.tournament.scheduleId === 'west-bend-2026')
    expect(westBend?.tournament).toMatchObject({
      name: 'West Bend High School',
      start: '2026-11-07',
      end: '2026-11-07',
    })
  })

  it('keeps two awards to one student at one tournament as two placings under that tournament', () => {
    const fort = results.groups.filter((group) => group.tournament.name === 'Fort Atkinson')
    expect(fort).toHaveLength(1)
    expect(fort[0]!.results.map((result) => result.placing)).toEqual(['first place', 'top speaker'])
  })

  it('gives the home page the three newest placings', () => {
    expect(newestResults(results).map(resultLine)).toEqual([
      'Second speaker, Junior Varsity Lincoln-Douglas: a Whitefish Bay debater',
      'Quarterfinalist, Novice Public Forum: Sam Okafor (2027) and Avery Chen (2029)',
      'First place, Varsity Lincoln-Douglas: Jordan Rivera (2028)',
    ])
  })

  it('passes the publishing-policy guard in the words the page prints', () => {
    const directory = resultsContent(SEASON_FIXTURE)
    const { errors } = checkPublishingPolicy({
      pages: resultsGuardedContent(directory),
      settings: loadSiteSettings(),
      consent: loadMediaConsent(directory),
    })
    expect(errors).toEqual([])
  })
})

/*
 * The team-level form is the build's choice, never the author's (the PM's ruling for this task):
 * whenever a named student's entry does not allow the full name this season, the result is
 * printed in team-level form with nothing changed in content/results.yaml. Both directions.
 */
describe('who a result names', () => {
  function onlyLine(yaml: string): string {
    const [group] = loadResults(resultsContent(yaml)).groups
    return resultLine(group!.results[0]!)
  }

  it('names a student with a current-season, full-name consent entry, with the graduation year', () => {
    expect(onlyLine(oneResult({ students: '[Jordan Rivera]' }))).toBe(
      'First place, Varsity Lincoln-Douglas: Jordan Rivera (2028)',
    )
  })

  it('names both partners when both may be named', () => {
    expect(
      onlyLine(oneResult({ event: 'public-forum', placing: 'finalist', students: '[Sam Okafor, Avery Chen]' })),
    ).toBe('Finalist, Varsity Public Forum: Sam Okafor (2027) and Avery Chen (2029)')
  })

  it('prints the team-level form when the only consent entry is from last season', () => {
    expect(onlyLine(oneResult({ students: '[Riley Moss]' }))).toBe(
      'First place, Varsity Lincoln-Douglas: a Whitefish Bay debater',
    )
  })

  it('prints the team-level form when the family asked for the first name only', () => {
    expect(onlyLine(oneResult({ students: '[Casey Park]' }))).toBe(
      'First place, Varsity Lincoln-Douglas: a Whitefish Bay debater',
    )
  })

  it('prints the team-level form for a partnership when either partner may not be named', () => {
    expect(
      onlyLine(oneResult({ event: 'policy', placing: 'octofinalist', students: '[Jordan Rivera, Riley Moss]' })),
    ).toBe('Octofinalist, Varsity Policy debate: a Whitefish Bay team')
  })

  it('takes a name off a result when its consent entry lapses, with no edit to the result', () => {
    const yaml = oneResult({ students: '[Jordan Rivera]' })
    const lapsed = { ...STUDENTS.jordan, season: '2025-26', dateChecked: '2025-09-12' }
    const [group] = loadResults(resultsContent(yaml, [lapsed])).groups
    expect(group!.results[0]!.named).toBe(false)
    expect(resultLine(group!.results[0]!)).not.toContain(STUDENTS.jordan.publishedName)
  })

  it('always publishes a team-level result, with no consent entry needed for anyone', () => {
    const [group] = loadResults(resultsContent(oneResult({ placing: 'champion' }), [])).groups
    expect(resultLine(group!.results[0]!)).toBe('Champion, Varsity Lincoln-Douglas: a Whitefish Bay debater')
  })
})

/*
 * acceptance criterion 2: what the build refuses, each naming the entry, the field and the rule.
 * No message repeats a student's name, because a build log carries none (Students 10).
 */
describe('what the build refuses', () => {
  it('a named student with no consent entry at all', () => {
    const message = loadError(resultsContent(oneResult({ students: '[Taylor Brooks]' })))
    expect(message).toMatch(
      /content\/results\.yaml: result 1 \(Fort Atkinson, 2026-10-17\), field students\.0: names a student with no entry in content\/media-consent\.yaml/,
    )
    expect(message).toMatch(/Students 2; Results and awards 1, 2 and 5/)
    expect(message).not.toContain('Taylor')
  })

  it('a partner event naming one partner', () => {
    const message = loadError(
      resultsContent(oneResult({ event: 'public-forum', students: '[Sam Okafor]' })),
    )
    expect(message).toMatch(/result 1 \(Fort Atkinson, 2026-10-17\), field students: names one partner of a partnership/)
    expect(message).toMatch(/Results and awards 1 and 2/)
    expect(message).not.toContain('Okafor')
  })

  it('an individual event naming two students', () => {
    expect(loadError(resultsContent(oneResult({ students: '[Jordan Rivera, Morgan Blake]' })))).toMatch(
      /field students: names 2 students for an individual event.*Results and awards 1/,
    )
  })

  it.each([
    ['lost in quarterfinals'],
    ['eliminated in octofinals'],
    ['dropped in semifinals'],
    ['did not break'],
  ])('a placing that is a loss: "%s"', (placing) => {
    expect(loadError(resultsContent(oneResult({ placing: `'${placing}'` })))).toMatch(
      /result 1 \(Fort Atkinson, 2026-10-17\), field placing: .* describes a loss.*Results and awards 4/,
    )
  })

  it.each([
    ['5-1 record'],
    ['went 4–2'],
    ['third place overall this season'],
    ['ranked second in the state'],
    ['228.5 speaker points'],
    ['two bids'],
  ])('a placing that is a record: "%s"', (placing) => {
    expect(loadError(resultsContent(oneResult({ placing: `'${placing}'` })))).toMatch(
      /field placing: .* is a record, not a placing.*Results and awards 3\)/,
    )
  })

  it('any placing outside the published set, listing the set', () => {
    expect(loadError(resultsContent(oneResult({ placing: 'honorable mention' })))).toMatch(
      /field placing: "honorable mention" is not a placing this site publishes\. Write one of: first place, /,
    )
  })

  it('an opponent student named in the tournament or the placing', () => {
    expect(
      loadError(resultsContent(oneResult({ tournament: "'Fort Atkinson, over Taylor Brooks'" }))),
    ).toMatch(/field tournament: holds a name the site has not been told about\. No opponent student is ever named.*Results and awards 5/)
    expect(loadError(resultsContent(oneResult({ placing: "'first place over Taylor Brooks'" })))).toMatch(
      /field placing: holds a name the site has not been told about.*Results and awards 5/,
    )
  })

  it('an opponent student put in `students`, which has no consent entry either', () => {
    expect(loadError(resultsContent(oneResult({ students: '[Taylor Brooks]' })))).toMatch(
      /an\s+opponent student never/,
    )
  })

  it('an email address or a phone number, wherever it is written', () => {
    expect(
      loadError(resultsContent(oneResult({ students: '[jordan.rivera@students.example.org]' }))),
    ).toMatch(/field students\.0: is an email address or a phone number, not a name.*Students 6/)
    expect(loadError(resultsContent(oneResult({ students: "['414-555-0142']" })))).toMatch(
      /field students\.0: is an email address or a phone number.*Students 6/,
    )
    expect(
      loadError(resultsContent(oneResult({ tournament: "'Fort Atkinson, call 414-555-0142'" }))),
    ).toMatch(/field tournament: holds an email address or a phone number.*Students 6/)
    expect(
      loadError(resultsContent(oneResult({ tournament: "'Fort Atkinson, coach@example.org'" }))),
    ).toMatch(/field tournament: holds an email address or a phone number/)
  })

  it('a result in a refusal names no student, not even by accident in its label', () => {
    const message = loadError(
      resultsContent(oneResult({ event: 'public-forum', students: '[Jordan Rivera]' })),
    )
    expect(message).not.toContain('Jordan')
    expect(message).not.toContain('Rivera')
  })
})

/* acceptance criterion 3: tournaments on and off the schedule. */
describe('the tournament a result was won at', () => {
  it('shows the name and date of a tournament that has come off the schedule', () => {
    expect(loadSchedule().tournaments.map((tournament) => tournament.name)).not.toContain('Neenah')
    const [group] = loadResults(resultsContent(oneResult({ tournament: 'Neenah', date: '2026-10-03' }))).groups
    expect(group!.tournament).toMatchObject({ name: 'Neenah', start: '2026-10-03', scheduleId: null })
  })

  it('takes an end date for an off-schedule tournament of more than one day', () => {
    const yaml = oneResult({ tournament: 'Neenah', date: '2026-10-02', end: '2026-10-03' })
    const [group] = loadResults(resultsContent(yaml)).groups
    expect(group!.tournament).toMatchObject({ start: '2026-10-02', end: '2026-10-03' })
  })

  it('fails the build on a schedule id that does not exist', () => {
    const yaml = oneResult({ tournament: '', date: '', scheduleId: 'fort-atkinson-2026' })
    expect(loadError(resultsContent(yaml))).toMatch(
      /result 1 \(fort-atkinson-2026\), field scheduleId: "fort-atkinson-2026" is not a tournament in content\/tournaments\.yaml\. A tournament that has come off the schedule is written with `tournament` and `date` instead/,
    )
  })

  it('refuses a schedule id together with a name or a date', () => {
    expect(loadError(resultsContent(oneResult({ scheduleId: 'west-bend-2026' })))).toMatch(
      /field tournament: goes with a tournament that is off the schedule/,
    )
  })

  it('refuses a result with neither', () => {
    expect(loadError(resultsContent(oneResult({ tournament: '', date: '' })))).toMatch(
      /result 1, field tournament: is required: name the tournament by its scheduleId/,
    )
  })

  it('refuses a date outside the season, which is almost always a mistyped year', () => {
    expect(loadError(resultsContent(oneResult({ date: '2025-10-17' })))).toMatch(
      /field date: 2025-10-17 is outside the 2026-27 season \(2026-08-01 to 2027-07-31\)/,
    )
  })

  it('refuses a date that does not exist, rather than letting the parser move it', () => {
    expect(loadError(resultsContent(oneResult({ date: '2026-09-31' })))).toMatch(
      /field date: must be a real date/,
    )
  })
})

describe('the shape of an entry', () => {
  it('refuses a field a result does not have, naming it', () => {
    expect(loadError(resultsContent(oneResult({ record: "'5-1'" })))).toMatch(
      /result 1 \(Fort Atkinson, 2026-10-17\), field record: is not a field a result has/,
    )
  })

  it('refuses an event that is not in content/events.yaml', () => {
    expect(loadError(resultsContent(oneResult({ event: 'congress' })))).toMatch(
      /field event: "congress" is not an event in content\/events\.yaml/,
    )
  })

  it('refuses a division it does not know', () => {
    expect(loadError(resultsContent(oneResult({ division: 'open' })))).toMatch(
      /field division: must be one of varsity, junior-varsity, novice/,
    )
  })

  it('refuses an em dash in the copy around the results', () => {
    const directory = resultsContent(SEASON_FIXTURE, Object.values(STUDENTS), {
      'results.yaml': (source) =>
        replaceOnce(
          '  empty: No results have been posted for this season yet.',
          '  empty: No results yet — check back soon.',
        )(source.replace(/^results:[\s\S]*$/m, 'results: []\n')),
    })
    expect(loadError(directory)).toMatch(/the labels use an em dash/)
  })

  it('refuses an acronym the page does not spell out', () => {
    const directory = resultsContent('', [], {
      'results.yaml': (source) =>
        replaceOnce(
          '  empty: No results have been posted for this season yet.',
          '  empty: No NSDA results have been posted for this season yet.',
        )(
          source.replace(/^results:[\s\S]*$/m, 'results: []\n'),
        ),
    })
    expect(() => loadResultsView(directory)).toThrow(/uses "NSDA" without spelling it out/)
  })

  it('publishes only placings at a single tournament', () => {
    for (const placing of PLACINGS) {
      expect(placingProblem(placing), placing).toBeNull()
    }
    expect(PLACINGS).toContain('first place')
    expect(PLACINGS).toContain('top speaker')
    expect(PLACINGS).toContain('quarterfinalist')
  })
})

/* acceptance criterion 1: the page and the home page, rendered with fixture content. */
describe('the /results/ page', () => {
  const settings = loadSiteSettings()
  const navigation = buildNavigation()

  function renderResults(yaml = SEASON_FIXTURE) {
    vi.spyOn(process, 'cwd').mockReturnValue(resultsSiteRoot(yaml))
    return render(
      <SiteFrame items={navigation.primary} strings={settings} utilityLinks={navigation.utility}>
        <ResultsPage />
      </SiteFrame>,
      { container: document.body },
    )
  }

  it('lists every tournament, newest first, with its date and each placing under it', () => {
    renderResults()
    const groups = [...document.querySelectorAll('.results-group')].map((group) => [
      group.querySelector('h3')?.textContent,
      group.querySelector('.results-group__dates')?.textContent,
      [...group.querySelectorAll('.results-group__result')].map((line) => line.textContent),
    ])
    expect(groups).toEqual(EXPECTED_GROUPS)
  })

  it('shows the event and division and the placing of every result', () => {
    renderResults()
    const placings = [...document.querySelectorAll('.result-line__placing')].map((node) => node.textContent)
    expect(placings).toEqual(['Second speaker', 'Quarterfinalist', 'First place', 'Top speaker', 'Semifinalist'])
  })

  it('opens the season band straight into the results, with no intro paragraph under its title', () => {
    renderResults()
    const band = document.getElementById('season-results') as HTMLElement
    expect(band.querySelector('.section__title')?.textContent).toBe(loadResultsView().seasonTitle)
    expect(band.querySelector('.section__intro')).toBeNull()
  })

  it('anchors each tournament, by schedule id or by name and date', () => {
    renderResults()
    expect(document.getElementById('west-bend-2026')).not.toBeNull()
    expect(document.getElementById('fort-atkinson-2026-10-17')).not.toBeNull()
  })

  it('says so, rather than showing an empty list, before the season has a result', () => {
    renderResults('')
    expect(document.querySelector('.results-list')).toBeNull()
    expect(document.querySelector('.results-empty')?.textContent).toBe(loadResults().labels.empty)
  })

  it('is in the primary navigation, straight after the schedule', () => {
    const hrefs = navigation.primary.map((link) => link.href)
    expect(hrefs).toContain(`/${RESULTS_SLUG}/`)
    expect(hrefs.indexOf(`/${RESULTS_SLUG}/`)).toBe(hrefs.indexOf('/schedule/') + 1)
  })

  it('has one h1, no heading level skipped, and no WCAG 2.1 AA violation', async () => {
    renderResults()
    expect(document.querySelectorAll('h1')).toHaveLength(1)
    const levels = [...document.querySelectorAll('h1, h2, h3, h4')].map((heading) => Number(heading.tagName[1]))
    for (const [index, level] of levels.entries()) {
      if (index > 0) {
        expect(level).toBeLessThanOrEqual(levels[index - 1]! + 1)
      }
    }
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

describe('the newest results on the home page', () => {
  const settings = loadSiteSettings()
  const home = loadHomeContent()

  function renderHome(yaml = SEASON_FIXTURE) {
    vi.spyOn(process, 'cwd').mockReturnValue(resultsSiteRoot(yaml))
    return render(
      <SiteFrame items={buildNavigation().primary} strings={settings}>
        <HomePage />
      </SiteFrame>,
      { container: document.body },
    )
  }

  function band(): HTMLElement {
    const element = document.getElementById('recent-results')
    expect(element, 'no #recent-results band on the home page').not.toBeNull()
    return element as HTMLElement
  }

  it('shows the three newest, each with its tournament and date', () => {
    renderHome()
    const items = [...band().querySelectorAll('.recent-results__item')].map((item) => [
      item.querySelector('.recent-results__line')?.textContent,
      item.querySelector('.recent-results__where')?.textContent,
    ])
    expect(items).toEqual([
      [
        'Second speaker, Junior Varsity Lincoln-Douglas: a Whitefish Bay debater',
        'Badgerland, Friday, November 13 to Saturday, November 14, 2026',
      ],
      [
        'Quarterfinalist, Novice Public Forum: Sam Okafor (2027) and Avery Chen (2029)',
        'West Bend High School, Saturday, November 7, 2026',
      ],
      ['First place, Varsity Lincoln-Douglas: Jordan Rivera (2028)', 'Fort Atkinson, Saturday, October 17, 2026'],
    ])
  })

  it('links to the results page', () => {
    renderHome()
    const link = within(band()).getByRole('link', { name: home.recentResults.action.label })
    expect(link.getAttribute('href')?.replace(/\/$/, '')).toBe(`/${RESULTS_SLUG}`)
    expect(home.recentResults.action.href).toBe(loadPage(RESULTS_SLUG).route)
  })

  it('sits after the email-updates band and before the entry points', () => {
    const { container } = renderHome()
    const ids = [...container.querySelectorAll('main > section')].map((section) => section.id)
    expect(ids.indexOf('recent-results')).toBe(ids.indexOf('email-updates') + 1)
    expect(ids.indexOf('start-here')).toBe(ids.indexOf('recent-results') + 1)
  })

  it('is left out while the season has no result', () => {
    renderHome('')
    expect(document.getElementById('recent-results')).toBeNull()
  })

  it('has no WCAG 2.1 AA violation', async () => {
    renderHome()
    const violations = await findAccessibilityViolations(band())
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

/**
 * Every word on the results page and in the home band comes from site/content/, as on every
 * other page (v1-e36-t03): this fails if a label is typed into a component instead.
 */
describe('the results page holds no copy of its own', () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(join(process.cwd(), directory)).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(join(process.cwd(), path)).isDirectory()) {
        return sourceFiles(path)
      }
      return /\.tsx?$/.test(entry) ? [path] : []
    })
  }

  const sources = [...sourceFiles('src/app'), ...sourceFiles('src/components')].map(
    (path) => [path, readFileSync(join(process.cwd(), path), 'utf8')] as const,
  )
  const { labels } = loadResults()
  const home = loadHomeContent().recentResults
  const copy = [
    loadPage(RESULTS_SLUG).title,
    labels.seasonTitle,
    labels.revised,
    labels.empty,
    labels.individual,
    labels.partners,
    labels.divisions['junior-varsity'],
    home.title,
    home.intro,
    home.action.label,
  ]

  it.each(copy.map((text) => [text.slice(0, 48), text] as const))('"%s" is not written into a component', (_label, text) => {
    for (const [path, source] of sources) {
      expect(source.includes(text), `${path} contains results copy`).toBe(false)
    }
  })
})

/**
 * The results the site actually ships, written out by hand from the coach's facts: Fort
 * Atkinson, Saturday, October 17, 2026, Varsity Lincoln-Douglas, first place and top speaker.
 * Checked for shape and never for who: the name is in site/content/ and nowhere else.
 */
describe('the results this site ships', () => {
  const shipped = loadResults()

  it('is the current season', () => {
    expect(shipped.season).toBe(loadSchedule().season)
    expect(shipped.season).toBe(loadMediaConsent().season)
  })

  it('is the coach’s first result: two placings at Fort Atkinson, in individual form', () => {
    expect(shipped.groups.map((group) => [group.tournament.name, group.tournament.start, group.tournament.scheduleId])).toEqual([
      ['Fort Atkinson', '2026-10-17', null],
    ])
    const results = shipped.groups[0]!.results
    expect(results.map((result) => [result.placing, result.division, result.event])).toEqual([
      ['first place', 'varsity', 'lincoln-douglas'],
      ['top speaker', 'varsity', 'lincoln-douglas'],
    ])
    for (const result of results) {
      expect(result.named).toBe(true)
      // "Full Name (graduation year)", by shape: one student, a name of two or more words.
      expect(result.who).toMatch(/^\p{L}[\p{L}.'’ -]* \p{L}[\p{L}.'’ -]* \(20\d\d\)$/u)
    }
    expect(new Set(results.map((result) => result.who)).size).toBe(1)
  })
})

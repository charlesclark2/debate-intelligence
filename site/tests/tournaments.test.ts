import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  calendarUid,
  datesOverlap,
  findOverlaps,
  formatDate,
  formatDateRange,
  isCalendarDate,
  loadSchedule,
  loadScheduleContent,
  loadScheduleView,
  nextDay,
} from '@/lib/tournaments'
import type { Tournament } from '@/lib/tournaments'

import { contentWith, editEntry, replaceOnce } from './schedule-fixture'

/**
 * content/tournaments.yaml and its loader (v1-e37-t02 acceptance criterion 1, and the overlap,
 * identity and build-date properties the spec's forbidden list names).
 *
 * The expected values below are written by hand from docs/data/2026-27-tournament-schedule.md,
 * the schedule as Charlie gave it on 2026-09-30, and not taken from the loader's output: a test
 * whose expectation came from the code it checks cannot catch that code dropping a row.
 */

/** Every row of the schedule document: name, first day, last day. */
const SEED: ReadonlyArray<readonly [string, string, string]> = [
  ['Neenah High School', '2026-10-10', '2026-10-10'],
  ['Fort Atkinson', '2026-10-17', '2026-10-17'],
  ['Ronald Reagan High School', '2026-10-24', '2026-10-24'],
  ['Iowa Caucus', '2026-10-23', '2026-10-25'],
  ['West Bend High School', '2026-10-30', '2026-10-30'],
  ['West Bend High School', '2026-11-07', '2026-11-07'],
  ['MinneApple', '2026-11-07', '2026-11-09'],
  ['Badgerland', '2026-11-13', '2026-11-14'],
  ['Brookfield East High School', '2026-11-21', '2026-11-21'],
  ['Glenbrooks', '2026-11-21', '2026-11-23'],
  ['Whitefish Bay home tournament', '2026-12-05', '2026-12-05'],
  ['Marquette University High School', '2026-12-12', '2026-12-12'],
  ['Blake', '2026-12-19', '2026-12-21'],
  ['Madison West', '2027-01-02', '2027-01-02'],
  ['Southern Wisconsin NSDA Qualifier', '2027-01-09', '2027-01-09'],
  ['Last Chance Qualifier', '2027-01-09', '2027-01-09'],
  ['Wisconsin State Debate Tournament', '2027-01-16', '2027-01-17'],
  ['Milwaukee NCFL Qualifier', '2027-01-23', '2027-01-23'],
  ['NCFL Nationals', '2027-05-29', '2027-05-30'],
  ['NSDA Nationals', '2027-06-13', '2027-06-18'],
]

/**
 * The overlapping pairs, worked out by hand from the document's dates. The task brief counted
 * three weekends; the dates give four, because both January 9 qualifiers are on one day.
 */
const OVERLAPPING_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ['iowa-caucus-2026', 'ronald-reagan-2026'],
  ['west-bend-2026', 'minneapple-2026'],
  ['brookfield-east-2026', 'glenbrooks-2026'],
  ['southern-wisconsin-nsda-qualifier-2027', 'last-chance-qualifier-2027'],
]

function loadError(directory: string): string {
  try {
    loadSchedule(directory)
  } catch (error) {
    return (error as Error).message
  }
  throw new Error('expected content/tournaments.yaml to be rejected, and it loaded')
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('the seed data', () => {
  const schedule = loadSchedule()

  it('holds every entry in the 2026-27 schedule document, and nothing else', () => {
    const loaded = schedule.tournaments.map((entry) => [entry.name, entry.start, entry.end])
    expect([...loaded].sort()).toEqual([...SEED].map((row) => [...row]).sort())
  })

  it('is for the 2026-27 season', () => {
    expect(schedule.season).toBe('2026-27')
  })

  it('puts the two national tournaments in their own section and nothing else there', () => {
    expect(
      schedule.tournaments.filter((entry) => entry.nationals).map((entry) => entry.name),
    ).toEqual(['NCFL Nationals', 'NSDA Nationals'])
  })

  it('records how each tournament the document says is online is held', () => {
    const held = (id: string) =>
      schedule.tournaments.find((entry) => entry.id === id)!.arrangements.map((group) => group.held)
    expect(held('iowa-caucus-2026')).toEqual(['online-at-school'])
    expect(held('west-bend-online-2026')).toEqual(['online-at-school'])
    expect(held('west-bend-2026')).toEqual(['in-person'])
  })

  it('splits Glenbrooks by event: Lincoln-Douglas and Public Forum online at school, Policy in Glenview', () => {
    const glenbrooks = schedule.tournaments.find((entry) => entry.id === 'glenbrooks-2026')!
    expect(glenbrooks.arrangements).toEqual([
      { events: ['public-forum', 'lincoln-douglas'], held: 'online-at-school', where: null, overnight: 'no' },
      { events: ['policy'], held: 'in-person', where: 'Glenview, Illinois', overnight: 'yes' },
    ])
  })

  it('records overnight as the document gives it', () => {
    const overnight = (id: string) =>
      schedule.tournaments.find((entry) => entry.id === id)!.arrangements.map((group) => group.overnight)
    expect(overnight('minneapple-2026')).toEqual(['yes'])
    expect(overnight('badgerland-2026')).toEqual(['possibly'])
    expect(overnight('blake-2026')).toEqual(['yes'])
    expect(overnight('neenah-2026')).toEqual(['no'])
  })

  it('marks the January 23 qualifier tentative and the December 5 home tournament conditional, with its condition', () => {
    const byId = new Map(schedule.tournaments.map((entry) => [entry.id, entry]))
    expect(byId.get('milwaukee-ncfl-qualifier-2027')?.status).toBe('tentative')
    expect(byId.get('milwaukee-ncfl-qualifier-2027')?.arrangements[0]?.where).toBe('To be announced')
    const home = byId.get('whitefish-bay-home-2026')!
    expect(home.status).toBe('conditional')
    expect(home.condition).toMatch(/enough families volunteer/)
    expect(home.condition).toMatch(/state tournament/)
  })

  it('lists the whole season in date order, the order worked out by hand', () => {
    expect(schedule.tournaments.map((entry) => entry.id)).toEqual([
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
      'ncfl-nationals-2027',
      'nsda-nationals-2027',
    ])
  })

  it('names no student, and carries no email address or phone number', () => {
    const text = schedule.tournaments
      .flatMap((entry) => [entry.name, entry.notes, entry.condition, ...entry.arrangements.map((g) => g.where)])
      .join('\n')
    expect(text).not.toMatch(/@/)
    expect(text).not.toMatch(/\d{3}[\s.-]\d{4}/)
  })
})

describe('the page does not depend on the day it was built', () => {
  /**
   * Deploys are manual, so a build from October has to be right in March. Nothing in the loader
   * may read the clock: with the system date moved past every tournament, the page still lists
   * every one of them, in the same order, in the same sections.
   */
  it('lists exactly the same tournaments whatever the date is', () => {
    const before = loadScheduleView()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2027-07-01T12:00:00Z'))
    const after = loadScheduleView()
    expect(after.seasonTournaments.map((entry) => entry.id)).toEqual(
      before.seasonTournaments.map((entry) => entry.id),
    )
    expect(after.nationals.map((entry) => entry.id)).toEqual(before.nationals.map((entry) => entry.id))
    expect(after.seasonTournaments).toHaveLength(18)
  })
})

describe('overlaps', () => {
  const schedule = loadSchedule()
  const overlaps = findOverlaps(schedule.tournaments)

  it('finds exactly the four pairs that share a day, worked out by hand', () => {
    const found = [...overlaps.entries()]
      .flatMap(([id, others]) => others.map((other) => [id, other.id].sort().join(' + ')))
    const expected = OVERLAPPING_PAIRS.flatMap((pair) => {
      const key = [...pair].sort().join(' + ')
      return [key, key]
    })
    expect(found.sort()).toEqual(expected.sort())
  })

  it('marks both entries of every pair, and drops neither', () => {
    for (const [left, right] of OVERLAPPING_PAIRS) {
      expect(overlaps.get(left)?.map((entry) => entry.id), left).toContain(right)
      expect(overlaps.get(right)?.map((entry) => entry.id), right).toContain(left)
    }
    expect(overlaps.size).toBe(SEED.length)
  })

  it('marks nothing on a tournament that shares no day with another', () => {
    expect(overlaps.get('neenah-2026')).toEqual([])
    expect(overlaps.get('badgerland-2026')).toEqual([])
  })

  const range = (start: string, end: string = start) => ({ start, end })

  it.each([
    ['the same single day', range('2026-11-07'), range('2026-11-07'), true],
    ['a day inside a range', range('2026-10-24'), range('2026-10-23', '2026-10-25'), true],
    ['a range starting on the last day of another', range('2026-11-09', '2026-11-10'), range('2026-11-07', '2026-11-09'), true],
    ['a range ending on the first day of another', range('2026-11-20', '2026-11-21'), range('2026-11-21', '2026-11-23'), true],
    ['consecutive days', range('2026-10-10'), range('2026-10-11'), false],
    ['a range ending the day before another starts', range('2026-11-13', '2026-11-14'), range('2026-11-15'), false],
  ])('%s: %s', (_name, left, right, expected) => {
    expect(datesOverlap(left, right)).toBe(expected)
    expect(datesOverlap(right, left)).toBe(expected)
  })
})

describe('calendar identity', () => {
  const base: Tournament = {
    id: 'glenbrooks-2026',
    position: 10,
    name: 'Glenbrooks',
    start: '2026-11-21',
    end: '2026-11-23',
    events: ['policy'],
    arrangements: [{ events: ['policy'], held: 'in-person', where: 'Glenview, Illinois', overnight: 'yes' }],
    status: 'confirmed',
    condition: null,
    signUpBy: null,
    notes: null,
    nationals: false,
  }

  it('is the entry id, written as a UID with the team domain', () => {
    expect(calendarUid(base)).toBe('tournament-glenbrooks-2026@wfbdebate.com')
  })

  it.each([
    ['notes', { notes: 'Varsity only.' }],
    ['dates', { start: '2026-11-20', end: '2026-11-22' }],
    ['name', { name: 'The Glenbrooks' }],
    ['status', { status: 'tentative' as const }],
    ['place', { arrangements: [{ ...base.arrangements[0]!, where: 'Northbrook, Illinois' }] }],
    ['position in the file', { position: 3 }],
  ])('does not change when the %s change', (_field, change) => {
    expect(calendarUid({ ...base, ...change })).toBe(calendarUid(base))
  })

  it('differs between entries', () => {
    const uids = loadSchedule().tournaments.map(calendarUid)
    expect(new Set(uids).size).toBe(uids.length)
  })
})

describe('an invalid entry fails the build, naming the entry and the field', () => {
  it.each([
    [
      'a missing required field',
      editEntry('badgerland-2026', (block) => block.replace('    held: in-person\n', '')),
      /tournament "badgerland-2026" \(entry 8\), field held: is required/,
    ],
    [
      'a date that does not exist',
      editEntry('neenah-2026', (block) => block.replace('2026-10-10', '2026-02-30')),
      /tournament "neenah-2026" \(entry 1\), field start: must be a real date/,
    ],
    [
      'an end before the start',
      editEntry('blake-2026', (block) => block.replace('end: 2026-12-21', 'end: 2026-12-18')),
      /tournament "blake-2026" \(entry 13\), field end: is before start/,
    ],
    [
      'a date outside the season',
      editEntry('neenah-2026', (block) => block.replace('2026-10-10', '2025-10-10')),
      /tournament "neenah-2026" \(entry 1\), field start: 2025-10-10 is outside the 2026-27 season/,
    ],
    [
      'an event that does not exist',
      editEntry('neenah-2026', (block) => block.replace('[public-forum, lincoln-douglas]', '[public-forum, congress]')),
      /tournament "neenah-2026" \(entry 1\), field events: "congress" is not an event/,
    ],
    [
      'a misspelt field',
      editEntry('blake-2026', (block) => block.replace('    notes:', '    note:')),
      /tournament "blake-2026" \(entry 13\), field note: is not a field a tournament has/,
    ],
    [
      'a conditional entry with no condition',
      editEntry('whitefish-bay-home-2026', (block) => block.replace(/    condition: >-\n(?: {6}.*\n)+/, '')),
      /tournament "whitefish-bay-home-2026" \(entry 11\), field condition: a conditional tournament needs `condition`/,
    ],
    [
      'a place on a tournament debated from the high school',
      editEntry('iowa-caucus-2026', (block) => block.replace('    held: online-at-school\n', '    held: online-at-school\n    where: Des Moines, Iowa\n')),
      /tournament "iowa-caucus-2026" \(entry 4\), field where: online-at-school is debated at Whitefish Bay High School/,
    ],
    [
      'an in-person tournament with no place',
      editEntry('neenah-2026', (block) => block.replace('    where: Neenah, Wisconsin\n', '')),
      /tournament "neenah-2026" \(entry 1\), field where: an in-person tournament needs `where`/,
    ],
    [
      'a whole-tournament field beside byEvent',
      editEntry('glenbrooks-2026', (block) => block.replace('    byEvent:\n', '    held: in-person\n    byEvent:\n')),
      /tournament "glenbrooks-2026" \(entry 10\), field held: goes inside each byEvent group/,
    ],
    [
      'an id without the year',
      editEntry('blake-2026', (block) => block.replace('id: blake-2026', 'id: blake')),
      /tournament "blake" \(entry 13\), field id: must be lower case words joined by hyphens, ending in the year/,
    ],
    [
      'a placeholder instead of a value',
      editEntry('milwaukee-ncfl-qualifier-2027', (block) => block.replace('where: To be announced', "where: '[[TBD: venue]]'")),
      /tournament "milwaukee-ncfl-qualifier-2027" \(entry 18\), field where: holds a \[\[TBD\]\] marker/,
    ],
    [
      'an em dash',
      editEntry('blake-2026', (block) => block.replace('notes: Varsity only.', 'notes: Varsity only — bring a coat.')),
      /tournament "blake-2026" \(entry 13\), field notes: uses an em dash/,
    ],
  ])('%s', (_name, edit, expected) => {
    expect(loadError(contentWith({ 'tournaments.yaml': edit }))).toMatch(expected)
  })

  it('a second entry with an id already in use, naming both', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('blake-2026', (block) => block.replace('id: blake-2026', 'id: neenah-2026')),
    })
    expect(loadError(directory)).toMatch(
      /tournament "neenah-2026" \(entry 13\), field id: "neenah-2026" is already used by tournament "neenah-2026" \(entry 1\)/,
    )
  })
})

/**
 * The publishing-policy guard on tournament text (acceptance criterion 1, second half). Every
 * case is checked in a dev build, the default, because tournament data fails the build in every
 * environment: there is no placeholder in it for a preview to show.
 */
describe('the publishing policy rejects what may never be written in tournament data', () => {
  it.each([
    [
      'an email address in the notes',
      editEntry('blake-2026', (block) => block.replace('notes: Varsity only.', 'notes: Questions to jordan.parent@example.com.')),
      /tournament "blake-2026" \(entry 13\), field notes: publishes the email address "jordan\.parent@example\.com"/,
    ],
    [
      'a phone number in the place',
      editEntry('badgerland-2026', (block) => block.replace('where: Madison, Wisconsin', 'where: Madison, Wisconsin. Call 414-555-0142')),
      /tournament "badgerland-2026" \(entry 8\), field where: publishes what looks like a phone number \("414-555-0142"\)/,
    ],
    [
      'a student name in the notes',
      editEntry('blake-2026', (block) => block.replace('notes: Varsity only.', 'notes: Varsity only. Jordan Rivera drives.')),
      /tournament "blake-2026" \(entry 13\), field notes: names "Jordan Rivera"/,
    ],
    [
      'a student name in a condition',
      editEntry('whitefish-bay-home-2026', (block) => block.replace('Our team hosts this tournament.', 'Our team hosts this tournament with Avery Chen.')),
      /tournament "whitefish-bay-home-2026" \(entry 11\), field condition: names "Avery Chen"/,
    ],
    [
      'a student name as the tournament name',
      editEntry('blake-2026', (block) => block.replace('name: Blake', 'name: Blake with Sam Okafor')),
      /tournament "blake-2026" \(entry 13\), field name: names "Sam Okafor"/,
    ],
  ])('%s', (_name, edit, expected) => {
    vi.stubEnv('SITE_ENV', 'dev')
    expect(loadError(contentWith({ 'tournaments.yaml': edit }))).toMatch(expected)
  })

  it('lets the allowlisted coach address through, as everywhere else on the site', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('blake-2026', (block) =>
        block.replace('notes: Varsity only.', 'notes: Varsity only. Questions to charles.clark@wfbschools.com.'),
      ),
    })
    expect(loadSchedule(directory).tournaments.find((entry) => entry.id === 'blake-2026')?.notes).toMatch(
      /charles\.clark@wfbschools\.com/,
    )
  })
})

describe('the words around the schedule', () => {
  it('never calls a tournament debated from the high school simply "online"', () => {
    const { held } = loadScheduleContent()
    expect(held['online-at-school']).toContain('Whitefish Bay High School')
    expect(held['online-at-school'].trim().toLowerCase()).not.toBe('online')
  })

  it('refuses a label for online-at-school that does not name the school', () => {
    const directory = contentWith({
      'schedule.yaml': replaceOnce('online-at-school: Online, debated at Whitefish Bay High School', 'online-at-school: Online'),
    })
    expect(() => loadScheduleContent(directory)).toThrowError(
      /the online-at-school label must say the tournament is debated at Whitefish Bay High School/,
    )
  })

  it('spells out every acronym the page uses: NSDA and NCFL appear only in tournament names', () => {
    const directory = contentWith({
      'schedule.yaml': replaceOnce(
        '  Two national tournaments close the season: the National Catholic Forensic League (NCFL) and the\n  National Speech and Debate Association (NSDA) national tournaments. Only students who qualify go.',
        '  Two national tournaments close the season. Only students who qualify go.',
      ),
    })
    expect(() => loadScheduleView(directory)).toThrowError(/uses "NSDA" without spelling it out/)
  })
})

describe('dates', () => {
  it.each([
    ['2026-10-10', true],
    ['2027-02-28', true],
    ['2026-02-29', false],
    ['2026-02-30', false],
    ['2026-13-01', false],
    ['2026-1-10', false],
  ])('%s is a calendar date: %s', (text, expected) => {
    expect(isCalendarDate(text)).toBe(expected)
  })

  it.each([
    ['2026-10-10', '2026-10-11'],
    ['2026-10-31', '2026-11-01'],
    ['2026-12-31', '2027-01-01'],
    ['2028-02-28', '2028-02-29'],
  ])('the day after %s is %s', (day, after) => {
    expect(nextDay(day)).toBe(after)
  })

  it('spells a day out in full', () => {
    expect(formatDate('2026-10-10')).toBe('Saturday, October 10, 2026')
    expect(formatDate('2027-01-23')).toBe('Saturday, January 23, 2027')
  })

  it('gives a range its year once, or twice when it crosses into the next year', () => {
    expect(formatDateRange({ start: '2026-10-23', end: '2026-10-25' })).toBe(
      'Friday, October 23 to Sunday, October 25, 2026',
    )
    expect(formatDateRange({ start: '2026-12-31', end: '2027-01-02' })).toBe(
      'Thursday, December 31, 2026 to Saturday, January 2, 2027',
    )
    expect(formatDateRange({ start: '2026-11-07', end: '2026-11-07' })).toBe('Saturday, November 7, 2026')
  })
})

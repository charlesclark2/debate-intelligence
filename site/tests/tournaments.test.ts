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

import { FIXTURE_SEASON, contentWith, replaceOnce } from './content-fixture'
import { editEntry } from './schedule-fixture'

/**
 * The tournaments.yaml loader (v1-e37-t02 acceptance criterion 1, and the overlap, identity and
 * build-date properties the spec's forbidden list names), on the synthetic season in
 * tests/fixtures/season/tournaments.yaml.
 *
 * The expected values below are written by hand from that file, and not taken from the loader's
 * output: a test whose expectation came from the code it checks cannot catch that code dropping a
 * row. They are never the shipped schedule's, which the coach edits every week (v1-e37-t10);
 * tests/shipped-content.test.ts checks what that file must always satisfy.
 */

/** Every entry of the synthetic season: name, first day, last day. */
const SEASON: ReadonlyArray<readonly [string, string, string]> = [
  ['Lantern Hill Invitational', '2026-12-05', '2026-12-05'],
  ['Harbor Point High School', '2026-10-10', '2026-10-10'],
  ['Granite Falls Round Robin', '2026-11-13', '2026-11-15'],
  ['NSDA Nationals', '2027-06-13', '2027-06-18'],
  ['Lakeshore Invitational', '2026-10-24', '2026-10-24'],
  ['Copper Creek Qualifier', '2027-01-09', '2027-01-09'],
  ['Northwoods Classic', '2026-11-06', '2026-11-07'],
  ['Pine Hollow Open', '2026-12-11', '2026-12-12'],
  ['Silver Lake Qualifier', '2027-01-09', '2027-01-09'],
  ['Eastbrook NCFL Qualifier', '2027-01-23', '2027-01-23'],
  ['Prairie Cup', '2026-11-14', '2026-11-14'],
  ['NCFL Nationals', '2027-05-29', '2027-05-30'],
]

/**
 * The overlapping pairs, worked out by hand from the fixture's dates: November 14 inside the
 * Granite Falls weekend, and both January 9 qualifiers on one day.
 */
const OVERLAPPING_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ['granite-falls-2026', 'prairie-cup-2026'],
  ['copper-creek-qualifier-2027', 'silver-lake-qualifier-2027'],
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

describe('a season, loaded', () => {
  const schedule = loadSchedule(contentWith())

  it('holds every entry in the file, and nothing else', () => {
    const loaded = schedule.tournaments.map((entry) => [entry.name, entry.start, entry.end])
    expect([...loaded].sort()).toEqual([...SEASON].map((row) => [...row]).sort())
  })

  it('is for the season the file names', () => {
    expect(schedule.season).toBe(FIXTURE_SEASON)
  })

  it('puts the two national tournaments in their own section and nothing else there', () => {
    expect(
      schedule.tournaments.filter((entry) => entry.nationals).map((entry) => entry.name),
    ).toEqual(['NCFL Nationals', 'NSDA Nationals'])
  })

  it('records how each tournament is held, by arrangement', () => {
    const held = (id: string) =>
      schedule.tournaments.find((entry) => entry.id === id)!.arrangements.map((group) => group.held)
    expect(held('harbor-point-online-2026')).toEqual(['online-at-school'])
    expect(held('lakeshore-2026')).toEqual(['in-person'])
    expect(held('pine-hollow-2026')).toEqual(['online-at-school', 'in-person'])
  })

  it('holds an entry without byEvent as one arrangement', () => {
    const graniteFalls = schedule.tournaments.find((entry) => entry.id === 'granite-falls-2026')!
    expect(graniteFalls.arrangements).toEqual([
      { events: ['policy'], held: 'in-person', where: 'Duluth, Minnesota', overnight: 'yes' },
    ])
  })

  it('splits an entry by event when byEvent is used: one arrangement per group', () => {
    const pineHollow = schedule.tournaments.find((entry) => entry.id === 'pine-hollow-2026')!
    expect(pineHollow.arrangements).toEqual([
      { events: ['public-forum', 'lincoln-douglas'], held: 'online-at-school', where: null, overnight: 'no' },
      { events: ['policy'], held: 'in-person', where: 'Evanston, Illinois', overnight: 'yes' },
    ])
  })

  it('records overnight as the file gives it', () => {
    const overnight = (id: string) =>
      schedule.tournaments.find((entry) => entry.id === id)!.arrangements.map((group) => group.overnight)
    expect(overnight('granite-falls-2026')).toEqual(['yes'])
    expect(overnight('northwoods-2026')).toEqual(['possibly'])
    expect(overnight('ncfl-nationals-2027')).toEqual(['yes'])
    expect(overnight('lakeshore-2026')).toEqual(['no'])
  })

  it('marks the January 23 qualifier tentative and the December 5 home tournament conditional, with its condition', () => {
    const byId = new Map(schedule.tournaments.map((entry) => [entry.id, entry]))
    expect(byId.get('eastbrook-ncfl-qualifier-2027')?.status).toBe('tentative')
    expect(byId.get('eastbrook-ncfl-qualifier-2027')?.arrangements[0]?.where).toBe('To be announced')
    const home = byId.get('lantern-hill-home-2026')!
    expect(home.status).toBe('conditional')
    expect(home.condition).toMatch(/enough families volunteer/)
    expect(home.condition).toMatch(/state tournament/)
  })

  it('lists the whole season in date order, the order worked out by hand', () => {
    // Same-day entries go by name, so Copper Creek comes before Silver Lake.
    expect(schedule.tournaments.map((entry) => entry.id)).toEqual([
      'harbor-point-online-2026',
      'lakeshore-2026',
      'northwoods-2026',
      'granite-falls-2026',
      'prairie-cup-2026',
      'lantern-hill-home-2026',
      'pine-hollow-2026',
      'copper-creek-qualifier-2027',
      'silver-lake-qualifier-2027',
      'eastbrook-ncfl-qualifier-2027',
      'ncfl-nationals-2027',
      'nsda-nationals-2027',
    ])
  })
})

describe('the page does not depend on the day it was built', () => {
  /**
   * Deploys are manual, so a build from October has to be right in March. Nothing in the loader
   * may read the clock: with the system date moved past every tournament, the page still lists
   * every one of them, in the same order, in the same sections.
   */
  it('lists exactly the same tournaments whatever the date is', () => {
    const directory = contentWith()
    const before = loadScheduleView(directory)
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2027-07-01T12:00:00Z'))
    const after = loadScheduleView(directory)
    expect(after.seasonTournaments.map((entry) => entry.id)).toEqual(
      before.seasonTournaments.map((entry) => entry.id),
    )
    expect(after.nationals.map((entry) => entry.id)).toEqual(before.nationals.map((entry) => entry.id))
    expect(after.seasonTournaments).toHaveLength(10)
  })
})

describe('overlaps', () => {
  const schedule = loadSchedule(contentWith())
  const overlaps = findOverlaps(schedule.tournaments)

  it('finds exactly the two pairs that share a day, worked out by hand', () => {
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
    expect(overlaps.size).toBe(SEASON.length)
  })

  it('marks nothing on a tournament that shares no day with another', () => {
    expect(overlaps.get('lakeshore-2026')).toEqual([])
    expect(overlaps.get('northwoods-2026')).toEqual([])
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
    id: 'granite-falls-2026',
    position: 3,
    name: 'Granite Falls Round Robin',
    start: '2026-11-13',
    end: '2026-11-15',
    events: ['policy'],
    arrangements: [{ events: ['policy'], held: 'in-person', where: 'Duluth, Minnesota', overnight: 'yes' }],
    status: 'confirmed',
    condition: null,
    signUpBy: null,
    notes: null,
    nationals: false,
  }

  it('is the entry id, written as a UID with the team domain', () => {
    expect(calendarUid(base)).toBe('tournament-granite-falls-2026@wfbdebate.com')
  })

  it.each([
    ['notes', { notes: 'Varsity only.' }],
    ['dates', { start: '2026-11-12', end: '2026-11-14' }],
    ['name', { name: 'The Granite Falls Round Robin' }],
    ['status', { status: 'tentative' as const }],
    ['place', { arrangements: [{ ...base.arrangements[0]!, where: 'Superior, Wisconsin' }] }],
    ['position in the file', { position: 9 }],
  ])('does not change when the %s change', (_field, change) => {
    expect(calendarUid({ ...base, ...change })).toBe(calendarUid(base))
  })

  it('differs between entries', () => {
    const uids = loadSchedule(contentWith()).tournaments.map(calendarUid)
    expect(new Set(uids).size).toBe(uids.length)
  })
})

describe('an invalid entry fails the build, naming the entry and the field', () => {
  it.each([
    [
      'a missing required field',
      editEntry('northwoods-2026', (block) => block.replace('    held: in-person\n', '')),
      /tournament "northwoods-2026" \(entry 7\), field held: is required/,
    ],
    [
      'a date that does not exist',
      editEntry('lakeshore-2026', (block) => block.replace('2026-10-24', '2026-02-30')),
      /tournament "lakeshore-2026" \(entry 5\), field start: must be a real date/,
    ],
    [
      'an end before the start',
      editEntry('granite-falls-2026', (block) => block.replace('end: 2026-11-15', 'end: 2026-11-12')),
      /tournament "granite-falls-2026" \(entry 3\), field end: is before start/,
    ],
    [
      'a date outside the season',
      editEntry('lakeshore-2026', (block) => block.replace('2026-10-24', '2025-10-24')),
      /tournament "lakeshore-2026" \(entry 5\), field start: 2025-10-24 is outside the 2026-27 season/,
    ],
    [
      'an event that does not exist',
      editEntry('lakeshore-2026', (block) => block.replace('[policy, lincoln-douglas, public-forum]', '[public-forum, congress]')),
      /tournament "lakeshore-2026" \(entry 5\), field events: "congress" is not an event/,
    ],
    [
      'a misspelt field',
      editEntry('granite-falls-2026', (block) => block.replace('    notes:', '    note:')),
      /tournament "granite-falls-2026" \(entry 3\), field note: is not a field a tournament has/,
    ],
    [
      'a conditional entry with no condition',
      editEntry('lantern-hill-home-2026', (block) => block.replace(/    condition: >-\n(?: {6}.*\n)+/, '')),
      /tournament "lantern-hill-home-2026" \(entry 1\), field condition: a conditional tournament needs `condition`/,
    ],
    [
      'a place on a tournament debated from the high school',
      editEntry('harbor-point-online-2026', (block) => block.replace('    held: online-at-school\n', '    held: online-at-school\n    where: Racine, Wisconsin\n')),
      /tournament "harbor-point-online-2026" \(entry 2\), field where: online-at-school is debated at Whitefish Bay High School/,
    ],
    [
      'an in-person tournament with no place',
      editEntry('lakeshore-2026', (block) => block.replace('    where: Racine, Wisconsin\n', '')),
      /tournament "lakeshore-2026" \(entry 5\), field where: an in-person tournament needs `where`/,
    ],
    [
      'a whole-tournament field beside byEvent',
      editEntry('pine-hollow-2026', (block) => block.replace('    byEvent:\n', '    held: in-person\n    byEvent:\n')),
      /tournament "pine-hollow-2026" \(entry 8\), field held: goes inside each byEvent group/,
    ],
    [
      'an id without the year',
      editEntry('granite-falls-2026', (block) => block.replace('id: granite-falls-2026', 'id: granite-falls')),
      /tournament "granite-falls" \(entry 3\), field id: must be lower case words joined by hyphens, ending in the year/,
    ],
    [
      'a placeholder instead of a value',
      editEntry('eastbrook-ncfl-qualifier-2027', (block) => block.replace('where: To be announced', "where: '[[TBD: venue]]'")),
      /tournament "eastbrook-ncfl-qualifier-2027" \(entry 10\), field where: holds a \[\[TBD\]\] marker/,
    ],
    [
      'an em dash',
      editEntry('granite-falls-2026', (block) => block.replace('notes: Varsity only.', 'notes: Varsity only — bring a coat.')),
      /tournament "granite-falls-2026" \(entry 3\), field notes: uses an em dash/,
    ],
  ])('%s', (_name, edit, expected) => {
    expect(loadError(contentWith({ 'tournaments.yaml': edit }))).toMatch(expected)
  })

  it('a second entry with an id already in use, naming both', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('granite-falls-2026', (block) =>
        block.replace('id: granite-falls-2026', 'id: lantern-hill-home-2026'),
      ),
    })
    expect(loadError(directory)).toMatch(
      /tournament "lantern-hill-home-2026" \(entry 3\), field id: "lantern-hill-home-2026" is already used by tournament "lantern-hill-home-2026" \(entry 1\)/,
    )
  })
})

/**
 * The publishing-policy guard on tournament text (acceptance criterion 1, second half). Every
 * case is checked in a dev build, the default, because tournament data fails the build in every
 * environment: there is no placeholder in it for a preview to show. The names planted are
 * invented and have no consent entry, not even a fixture one.
 */
describe('the publishing policy rejects what may never be written in tournament data', () => {
  it.each([
    [
      'an email address in the notes',
      editEntry('granite-falls-2026', (block) => block.replace('notes: Varsity only.', 'notes: Questions to jordan.parent@example.com.')),
      /tournament "granite-falls-2026" \(entry 3\), field notes: publishes the email address "jordan\.parent@example\.com"/,
    ],
    [
      'a phone number in the place',
      editEntry('northwoods-2026', (block) => block.replace('where: Wausau, Wisconsin', 'where: Wausau, Wisconsin. Call 414-555-0142')),
      /tournament "northwoods-2026" \(entry 7\), field where: publishes what looks like a phone number \("414-555-0142"\)/,
    ],
    [
      'a student name in the notes',
      editEntry('granite-falls-2026', (block) => block.replace('notes: Varsity only.', 'notes: Varsity only. Taylor Brooks drives.')),
      /tournament "granite-falls-2026" \(entry 3\), field notes: names "Taylor Brooks"/,
    ],
    [
      'a student name in a condition',
      editEntry('lantern-hill-home-2026', (block) => block.replace('Our team hosts this tournament.', 'Our team hosts this tournament with Quinn Harlow.')),
      /tournament "lantern-hill-home-2026" \(entry 1\), field condition: names "Quinn Harlow"/,
    ],
    [
      'a student name as the tournament name',
      editEntry('granite-falls-2026', (block) => block.replace('name: Granite Falls Round Robin', 'name: Granite Falls Round Robin with Rowan Ellis')),
      /tournament "granite-falls-2026" \(entry 3\), field name: names "Rowan Ellis"/,
    ],
  ])('%s', (_name, edit, expected) => {
    vi.stubEnv('SITE_ENV', 'dev')
    expect(loadError(contentWith({ 'tournaments.yaml': edit }))).toMatch(expected)
  })

  it('lets the allowlisted coach address through, as everywhere else on the site', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('granite-falls-2026', (block) =>
        block.replace('notes: Varsity only.', 'notes: Varsity only. Questions to charles.clark@wfbschools.com.'),
      ),
    })
    expect(loadSchedule(directory).tournaments.find((entry) => entry.id === 'granite-falls-2026')?.notes).toMatch(
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

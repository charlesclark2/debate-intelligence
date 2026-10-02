import ICAL from 'ical.js'
import { describe, expect, it } from 'vitest'

import {
  MAX_LINE_OCTETS,
  buildScheduleCalendar,
  calendarHttpsUrl,
  calendarWebcalUrl,
  escapeText,
  foldLine,
} from '@/lib/icalendar'
import { loadScheduleView } from '@/lib/tournaments'

import { contentWith, editEntry } from './schedule-fixture'

/**
 * The calendar file (v1-e37-t02 acceptance criterion 3).
 *
 * The file is read back with ical.js, Mozilla's iCalendar library, rather than with anything in
 * src/lib/icalendar.ts. A parser written beside the generator would share its misreadings of RFC
 * 5545, and a round trip through the two would agree on exactly the mistakes it exists to catch.
 *
 * The expected dates are written by hand from docs/data/2026-27-tournament-schedule.md, with the
 * end date worked out as the day after the last day, because an iCalendar DTEND is exclusive.
 */

const SITE = 'https://wfbdebate.example.invalid'

interface ParsedEvent {
  uid: string
  summary: string
  description: string
  location: string | null
  start: string
  end: string
  startIsDate: boolean
  endIsDate: boolean
  status: string
}

function parse(ics: string): { calendar: ICAL.Component; events: ParsedEvent[] } {
  const calendar = new ICAL.Component(ICAL.parse(ics))
  const events = calendar.getAllSubcomponents('vevent').map((component) => {
    const event = new ICAL.Event(component)
    return {
      uid: event.uid,
      summary: event.summary,
      description: event.description,
      location: (component.getFirstPropertyValue('location') as string | null) ?? null,
      start: event.startDate.toString(),
      end: event.endDate.toString(),
      startIsDate: event.startDate.isDate,
      endIsDate: event.endDate.isDate,
      status: String(component.getFirstPropertyValue('status')),
    }
  })
  return { calendar, events }
}

function calendarFrom(directory?: string): string {
  return buildScheduleCalendar(loadScheduleView(directory), SITE)
}

const shipped = calendarFrom()
const { calendar, events } = parse(shipped)
const byUid = new Map(events.map((event) => [event.uid, event]))
const event = (id: string) => {
  const found = byUid.get(`tournament-${id}@wfbdebate.com`)
  if (!found) throw new Error(`no event for ${id}`)
  return found
}

describe('the calendar parses with an independent parser', () => {
  it('is one VCALENDAR with one event per tournament, nationals included', () => {
    expect(calendar.name).toBe('vcalendar')
    expect(events).toHaveLength(20)
    expect(new Set(events.map((entry) => entry.uid)).size).toBe(20)
  })

  it('names itself for the app that subscribes to it', () => {
    expect(calendar.getFirstPropertyValue('x-wr-calname')).toBe('Whitefish Bay Debate tournaments')
    expect(calendar.getFirstPropertyValue('version')).toBe('2.0')
    expect(calendar.getFirstPropertyValue('prodid')).toBeTruthy()
  })
})

describe('all-day and multi-day dates', () => {
  it('makes every event all-day: VALUE=DATE at both ends', () => {
    for (const entry of events) {
      expect(entry.startIsDate, entry.summary).toBe(true)
      expect(entry.endIsDate, entry.summary).toBe(true)
    }
    expect(shipped).toMatch(/^DTSTART;VALUE=DATE:\d{8}\r$/m)
    expect(shipped).not.toMatch(/^DTSTART:/m)
  })

  it.each([
    // [id, first day, exclusive end: the day after the last day]
    ['neenah-2026', '2026-10-10', '2026-10-11'],
    ['iowa-caucus-2026', '2026-10-23', '2026-10-26'],
    ['minneapple-2026', '2026-11-07', '2026-11-10'],
    ['badgerland-2026', '2026-11-13', '2026-11-15'],
    ['glenbrooks-2026', '2026-11-21', '2026-11-24'],
    ['blake-2026', '2026-12-19', '2026-12-22'],
    ['wisconsin-state-2027', '2027-01-16', '2027-01-18'],
    ['ncfl-nationals-2027', '2027-05-29', '2027-05-31'],
    ['nsda-nationals-2027', '2027-06-13', '2027-06-19'],
  ])('%s runs from %s with an exclusive end of %s', (id, start, end) => {
    expect(event(id).start).toBe(start)
    expect(event(id).end).toBe(end)
  })

  it('carries an exclusive end across a month boundary', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('blake-2026', (block) =>
        block.replace('start: 2026-12-19', 'start: 2026-12-30').replace('end: 2026-12-21', 'end: 2026-12-31'),
      ),
    })
    const moved = parse(calendarFrom(directory)).events.find((entry) => entry.summary === 'Blake')!
    expect([moved.start, moved.end]).toEqual(['2026-12-30', '2027-01-01'])
  })
})

describe('identity: a UID survives an edit to everything else', () => {
  const edited = parse(
    calendarFrom(
      contentWith({
        'tournaments.yaml': (source) =>
          editEntry('glenbrooks-2026', (block) =>
            block.replace('notes: Varsity only.', 'notes: Varsity only. Bring a coat; it is cold.'),
          )(
            editEntry('neenah-2026', (block) =>
              block.replace('    status: confirmed\n', '    status: confirmed\n    notes: Bus at 6:30 AM.\n'),
            )(source),
          ),
      }),
    ),
  ).events

  it('keeps every UID when notes are edited, added or removed', () => {
    expect(edited.map((entry) => entry.uid)).toEqual(events.map((entry) => entry.uid))
  })

  it('changes the edited events, so the UIDs above are the same events with new notes', () => {
    const glenbrooks = edited.find((entry) => entry.uid === event('glenbrooks-2026').uid)!
    expect(glenbrooks.description).toContain('Bring a coat; it is cold.')
    expect(event('glenbrooks-2026').description).not.toContain('Bring a coat')
    const neenah = edited.find((entry) => entry.uid === event('neenah-2026').uid)!
    expect(neenah.description).toContain('Bus at 6:30 AM.')
  })

  it('keeps the UID when the dates are corrected', () => {
    const moved = parse(
      calendarFrom(
        contentWith({
          'tournaments.yaml': editEntry('badgerland-2026', (block) =>
            block.replace('start: 2026-11-13', 'start: 2026-11-12'),
          ),
        }),
      ),
    ).events
    const badgerland = moved.find((entry) => entry.summary === 'Badgerland')!
    expect(badgerland.uid).toBe(event('badgerland-2026').uid)
    expect(badgerland.start).toBe('2026-11-12')
  })
})

describe('escaping, folding and line endings', () => {
  it('ends every line in CRLF, and has no bare LF or CR', () => {
    expect(shipped.endsWith('\r\n')).toBe(true)
    expect(shipped.replace(/\r\n/g, '')).not.toMatch(/[\r\n]/)
  })

  it(`keeps every line to ${MAX_LINE_OCTETS} octets of UTF-8`, () => {
    for (const line of shipped.split('\r\n')) {
      expect(new TextEncoder().encode(line).length, line).toBeLessThanOrEqual(MAX_LINE_OCTETS)
    }
  })

  it('folds long lines, and the parser unfolds them back to the exact text', () => {
    expect(shipped).toMatch(/\r\n [^\r]/)
    expect(event('whitefish-bay-home-2026').description).toContain(
      'Our team hosts this tournament. Our students compete in it only if enough families volunteer ' +
        'to help run it and some students still need qualifying results, called legs, for the state ' +
        'tournament.',
    )
  })

  /**
   * Every character RFC 5545 makes special in a TEXT value, plus characters of two, three and
   * four bytes in UTF-8 placed so that a fold lands on them: each must come back exactly.
   */
  it('round-trips commas, semicolons, backslashes, newlines and multi-byte characters', () => {
    const awkward =
      'Café; crêpes, and a C:\\Teams\\Debate path. ' + 'é'.repeat(40) + ' 日本語の大会 ' + '🎉'.repeat(20)
    const directory = contentWith({
      'tournaments.yaml': editEntry('blake-2026', (block) =>
        block.replace('notes: Varsity only.', `notes: ${JSON.stringify(awkward)}`),
      ),
    })
    const ics = calendarFrom(directory)
    for (const line of ics.split('\r\n')) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(MAX_LINE_OCTETS)
    }
    const blake = parse(ics).events.find((entry) => entry.summary === 'Blake')!
    expect(blake.description).toContain(`Notes: ${awkward}`)
    // And the description's own line breaks survive as line breaks.
    expect(blake.description.split('\n')[0]).toBe('Where: Minneapolis, Minnesota')
  })

  it.each([
    ['a, b', 'a\\, b'],
    ['a; b', 'a\\; b'],
    ['a\\b', 'a\\\\b'],
    ['a\nb', 'a\\nb'],
    ['\\,', '\\\\\\,'],
  ])('escapes %j as %j', (raw, escaped) => {
    expect(escapeText(raw)).toBe(escaped)
  })

  it('never splits a character across a fold', () => {
    const folded = foldLine(`DESCRIPTION:${'x'.repeat(62)}🎉🎉🎉`)
    for (const line of folded.split('\r\n')) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(MAX_LINE_OCTETS)
      expect(line).not.toMatch(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/)
    }
    expect(folded.replace(/\r\n /g, '')).toBe(`DESCRIPTION:${'x'.repeat(62)}🎉🎉🎉`)
  })
})

describe('what a parent sees in their calendar app', () => {
  it('says in the title when a tournament may not happen', () => {
    expect(event('milwaukee-ncfl-qualifier-2027').summary).toBe('Tentative: Milwaukee NCFL Qualifier')
    expect(event('milwaukee-ncfl-qualifier-2027').status).toBe('TENTATIVE')
    expect(event('whitefish-bay-home-2026').summary).toBe('Conditional: Whitefish Bay home tournament')
    expect(event('whitefish-bay-home-2026').status).toBe('TENTATIVE')
    expect(event('neenah-2026').summary).toBe('Neenah High School')
    expect(event('neenah-2026').status).toBe('CONFIRMED')
  })

  it('gives a tournament debated from the high school the high school as its place', () => {
    expect(event('iowa-caucus-2026').location).toBe('Whitefish Bay High School')
    expect(event('iowa-caucus-2026').description).toContain(
      'How it is held: Online, debated at Whitefish Bay High School',
    )
  })

  it('gives Glenbrooks both places, and says which event is held where', () => {
    const glenbrooks = event('glenbrooks-2026')
    expect(glenbrooks.location).toBe('Whitefish Bay High School; Glenview, Illinois')
    expect(glenbrooks.description).toContain(
      'Public Forum, Lincoln-Douglas: Online, debated at Whitefish Bay High School. Overnight: No.',
    )
    expect(glenbrooks.description).toContain('Policy debate: In person, Glenview, Illinois. Overnight: Yes.')
  })

  it('tells both entries of an overlap about the other', () => {
    expect(event('ronald-reagan-2026').description).toContain(
      'Same dates as: Iowa Caucus (Friday, October 23 to Sunday, October 25, 2026)',
    )
    expect(event('iowa-caucus-2026').description).toContain(
      'Same dates as: Ronald Reagan High School (Saturday, October 24, 2026)',
    )
  })

  it('links each event back to its entry on the schedule page', () => {
    expect(event('blake-2026').description).toContain(`${SITE}/schedule/#blake-2026`)
    expect(shipped).toContain(`URL:${SITE}/schedule/#blake-2026\r\n`)
  })
})

describe('a rebuild of the same schedule is the same file', () => {
  it('stamps every event with the revised date, not the build time', () => {
    const stamps = [...shipped.matchAll(/^DTSTAMP:(.*)\r$/gm)].map((match) => match[1])
    expect(stamps).toHaveLength(20)
    expect(new Set(stamps)).toEqual(new Set(['20261001T000000Z']))
  })

  it('is byte for byte identical when built twice', () => {
    expect(calendarFrom()).toBe(shipped)
  })
})

describe('the subscribe addresses', () => {
  it('serves the file over https and offers the same address as webcal', () => {
    expect(calendarHttpsUrl(SITE)).toBe('https://wfbdebate.example.invalid/schedule.ics')
    expect(calendarWebcalUrl(SITE)).toBe('webcal://wfbdebate.example.invalid/schedule.ics')
  })
})

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

import { contentWith } from './content-fixture'
import { editEntry } from './schedule-fixture'

/**
 * The calendar file (v1-e37-t02 acceptance criterion 3).
 *
 * The file is read back with ical.js, Mozilla's iCalendar library, rather than with anything in
 * src/lib/icalendar.ts. A parser written beside the generator would share its misreadings of RFC
 * 5545, and a round trip through the two would agree on exactly the mistakes it exists to catch.
 *
 * The calendar is built from the synthetic season in tests/fixtures/season/tournaments.yaml, never
 * from the shipped schedule the coach edits every week (v1-e37-t10). The expected dates are written
 * by hand from that file, with the end date worked out as the day after the last day, because an
 * iCalendar DTEND is exclusive.
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

function calendarFrom(directory: string): string {
  return buildScheduleCalendar(loadScheduleView(directory), SITE)
}

const built = calendarFrom(contentWith())
const { calendar, events } = parse(built)
const byUid = new Map(events.map((event) => [event.uid, event]))
const event = (id: string) => {
  const found = byUid.get(`tournament-${id}@wfbdebate.com`)
  if (!found) throw new Error(`no event for ${id}`)
  return found
}

describe('the calendar parses with an independent parser', () => {
  it('is one VCALENDAR with one event per tournament, nationals included', () => {
    expect(calendar.name).toBe('vcalendar')
    expect(events).toHaveLength(12)
    expect(new Set(events.map((entry) => entry.uid)).size).toBe(12)
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
    expect(built).toMatch(/^DTSTART;VALUE=DATE:\d{8}\r$/m)
    expect(built).not.toMatch(/^DTSTART:/m)
  })

  it.each([
    // [id, first day, exclusive end: the day after the last day]
    ['lakeshore-2026', '2026-10-24', '2026-10-25'],
    ['northwoods-2026', '2026-11-06', '2026-11-08'],
    ['granite-falls-2026', '2026-11-13', '2026-11-16'],
    ['pine-hollow-2026', '2026-12-11', '2026-12-13'],
    ['copper-creek-qualifier-2027', '2027-01-09', '2027-01-10'],
    ['ncfl-nationals-2027', '2027-05-29', '2027-05-31'],
    ['nsda-nationals-2027', '2027-06-13', '2027-06-19'],
  ])('%s runs from %s with an exclusive end of %s', (id, start, end) => {
    expect(event(id).start).toBe(start)
    expect(event(id).end).toBe(end)
  })

  it('carries an exclusive end across a month boundary', () => {
    const directory = contentWith({
      'tournaments.yaml': editEntry('granite-falls-2026', (block) =>
        block.replace('start: 2026-11-13', 'start: 2026-12-30').replace('end: 2026-11-15', 'end: 2026-12-31'),
      ),
    })
    const moved = parse(calendarFrom(directory)).events.find((entry) => entry.summary === 'Granite Falls Round Robin')!
    expect([moved.start, moved.end]).toEqual(['2026-12-30', '2027-01-01'])
  })
})

describe('identity: a UID survives an edit to everything else', () => {
  const edited = parse(
    calendarFrom(
      contentWith({
        'tournaments.yaml': (source) =>
          editEntry('granite-falls-2026', (block) =>
            block.replace('notes: Varsity only.', 'notes: Varsity only. Bring a coat; it is cold.'),
          )(
            editEntry('lakeshore-2026', (block) =>
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
    const graniteFalls = edited.find((entry) => entry.uid === event('granite-falls-2026').uid)!
    expect(graniteFalls.description).toContain('Bring a coat; it is cold.')
    expect(event('granite-falls-2026').description).not.toContain('Bring a coat')
    const lakeshore = edited.find((entry) => entry.uid === event('lakeshore-2026').uid)!
    expect(lakeshore.description).toContain('Bus at 6:30 AM.')
  })

  it('keeps the UID when the dates are corrected', () => {
    const moved = parse(
      calendarFrom(
        contentWith({
          'tournaments.yaml': editEntry('northwoods-2026', (block) =>
            block.replace('start: 2026-11-06', 'start: 2026-11-05'),
          ),
        }),
      ),
    ).events
    const northwoods = moved.find((entry) => entry.summary === 'Northwoods Classic')!
    expect(northwoods.uid).toBe(event('northwoods-2026').uid)
    expect(northwoods.start).toBe('2026-11-05')
  })
})

describe('escaping, folding and line endings', () => {
  it('ends every line in CRLF, and has no bare LF or CR', () => {
    expect(built.endsWith('\r\n')).toBe(true)
    expect(built.replace(/\r\n/g, '')).not.toMatch(/[\r\n]/)
  })

  it(`keeps every line to ${MAX_LINE_OCTETS} octets of UTF-8`, () => {
    for (const line of built.split('\r\n')) {
      expect(new TextEncoder().encode(line).length, line).toBeLessThanOrEqual(MAX_LINE_OCTETS)
    }
  })

  it('folds long lines, and the parser unfolds them back to the exact text', () => {
    expect(built).toMatch(/\r\n [^\r]/)
    expect(event('lantern-hill-home-2026').description).toContain(
      'Our team hosts this tournament. Our students compete in it only if enough families volunteer ' +
        'to help run it and some students still need a qualifying result for the state tournament.',
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
      'tournaments.yaml': editEntry('granite-falls-2026', (block) =>
        block.replace('notes: Varsity only.', `notes: ${JSON.stringify(awkward)}`),
      ),
    })
    const ics = calendarFrom(directory)
    for (const line of ics.split('\r\n')) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(MAX_LINE_OCTETS)
    }
    const graniteFalls = parse(ics).events.find((entry) => entry.summary === 'Granite Falls Round Robin')!
    expect(graniteFalls.description).toContain(`Notes: ${awkward}`)
    // And the description's own line breaks survive as line breaks.
    expect(graniteFalls.description.split('\n')[0]).toBe('Where: Duluth, Minnesota')
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
    expect(event('eastbrook-ncfl-qualifier-2027').summary).toBe('Tentative: Eastbrook NCFL Qualifier')
    expect(event('eastbrook-ncfl-qualifier-2027').status).toBe('TENTATIVE')
    expect(event('lantern-hill-home-2026').summary).toBe('Conditional: Lantern Hill Invitational')
    expect(event('lantern-hill-home-2026').status).toBe('TENTATIVE')
    expect(event('lakeshore-2026').summary).toBe('Lakeshore Invitational')
    expect(event('lakeshore-2026').status).toBe('CONFIRMED')
  })

  it('gives a tournament debated from the high school the high school as its place', () => {
    expect(event('harbor-point-online-2026').location).toBe('Whitefish Bay High School')
    expect(event('harbor-point-online-2026').description).toContain(
      'How it is held: Online, debated at Whitefish Bay High School',
    )
  })

  it('gives a tournament held one way its one place', () => {
    expect(event('granite-falls-2026').location).toBe('Duluth, Minnesota')
  })

  it('gives a tournament split by event both places, and says which event is held where', () => {
    const pineHollow = event('pine-hollow-2026')
    expect(pineHollow.location).toBe('Whitefish Bay High School; Evanston, Illinois')
    expect(pineHollow.description).toContain(
      'Public Forum, Lincoln-Douglas: Online, debated at Whitefish Bay High School. Overnight: No.',
    )
    expect(pineHollow.description).toContain('Policy debate: In person, Evanston, Illinois. Overnight: Yes.')
  })

  it('tells both entries of an overlap about the other', () => {
    expect(event('prairie-cup-2026').description).toContain(
      'Same dates as: Granite Falls Round Robin (Friday, November 13 to Sunday, November 15, 2026)',
    )
    expect(event('granite-falls-2026').description).toContain(
      'Same dates as: Prairie Cup (Saturday, November 14, 2026)',
    )
  })

  it('links each event back to its entry on the schedule page', () => {
    expect(event('lakeshore-2026').description).toContain(`${SITE}/schedule/#lakeshore-2026`)
    expect(built).toContain(`URL:${SITE}/schedule/#lakeshore-2026\r\n`)
  })
})

describe('a rebuild of the same schedule is the same file', () => {
  it('stamps every event with the revised date, not the build time', () => {
    const stamps = [...built.matchAll(/^DTSTAMP:(.*)\r$/gm)].map((match) => match[1])
    expect(stamps).toHaveLength(12)
    expect(new Set(stamps)).toEqual(new Set(['20260915T000000Z']))
  })

  it('is byte for byte identical when built twice', () => {
    expect(calendarFrom(contentWith())).toBe(built)
  })
})

describe('the subscribe addresses', () => {
  it('serves the file over https and offers the same address as webcal', () => {
    expect(calendarHttpsUrl(SITE)).toBe('https://wfbdebate.example.invalid/schedule.ics')
    expect(calendarWebcalUrl(SITE)).toBe('webcal://wfbdebate.example.invalid/schedule.ics')
  })
})
